import os
import time
import json
import base64
import requests
from celery import Celery
from sqlalchemy import select, func, update
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from requests.exceptions import ReadTimeout, RequestException  # ← 新增这一行
from app.models import Dataset, Task, Job

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery = Celery("aiplatform", broker=BROKER_URL, backend=RESULT_BACKEND)
celery.conf.broker_connection_retry_on_startup = (
    os.environ.get("CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP", "true").lower() == "true"
)
# 进程内缓存 access：避免频繁 refresh
_ACCESS_CACHE = {"token": None, "exp_at": 0}


@celery.task(name="ping")
def ping():
    return {"ok": True}


def _env_required(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise RuntimeError(f"{name} is empty, please set it in .env")
    return v


def _ls_base() -> str:
    return _env_required("LS_BASE_URL").rstrip("/")


def _ls_project_id() -> int:
    return int(_env_required("LS_PROJECT_ID"))


def _ls_refresh_token() -> str:
    """
    这里放 Label Studio UI 里复制的 Personal Access Token（JWT refresh）。
    注意：你那边组织已禁用 legacy Token auth，所以不能用 authtoken_token.key。
    """
    tok = _env_required("LS_API_TOKEN")
    # 轻量校验：refresh JWT 一般是三段式
    if tok.count(".") != 2:
        raise RuntimeError(
            "LS_API_TOKEN does not look like a JWT refresh token. "
            "Make sure you copied Personal Access Token (refresh JWT) from Label Studio UI."
        )
    return tok


def _raise_with_detail(r: requests.Response, prefix: str):
    body = (r.text or "")[:500]
    raise RuntimeError(f"{prefix}: HTTP {r.status_code} - {body}")


def _jwt_exp_unix(token: str) -> int:
    """
    从 JWT payload 解析 exp（不做签名校验，只用于缓存过期时间）。
    """
    try:
        payload_b64 = token.split(".")[1]
        pad = "=" * (-len(payload_b64) % 4)
        data = base64.urlsafe_b64decode(payload_b64 + pad)
        obj = json.loads(data.decode("utf-8"))
        return int(obj.get("exp") or 0)
    except Exception:
        return 0


def _fetch_access_token() -> str:
    """
    用 refresh token 换 access token:
      POST /api/token/refresh(/)  {"refresh": "<refresh_jwt>"}
    """
    base = _ls_base()
    refresh = _ls_refresh_token()

    for path in ("/api/token/refresh", "/api/token/refresh/"):
        url = base + path
        r = requests.post(
            url,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={"refresh": refresh},
            timeout=30,
        )
        if r.ok:
            data = r.json() if r.text else {}
            access = (data.get("access") or "").strip()
            if not access:
                _raise_with_detail(r, "LS refresh ok but access missing")

            exp = _jwt_exp_unix(access)
            now = int(time.time())

            # 如果解析不到 exp，就保守缓存 60 秒；能解析到就缓存到过期前 30 秒
            if exp > now:
                _ACCESS_CACHE["token"] = access
                _ACCESS_CACHE["exp_at"] = exp - 30
            else:
                _ACCESS_CACHE["token"] = access
                _ACCESS_CACHE["exp_at"] = now + 60

            return access

        # 404 继续试另一个路径；其他错误直接抛，写进 job.message
        if r.status_code != 404:
            _raise_with_detail(r, "LS refresh access token failed")

    raise RuntimeError("LS refresh access token failed: endpoint not found")


def _get_access_token() -> str:
    now = int(time.time())
    if _ACCESS_CACHE["token"] and now < _ACCESS_CACHE["exp_at"]:
        return _ACCESS_CACHE["token"]
    return _fetch_access_token()


def _ls_headers(force_refresh: bool = False):
    """
    Label Studio API 鉴权：必须 Bearer <access>
    access 由 refresh(PAT) 动态换取
    """
    if force_refresh:
        _ACCESS_CACHE["token"] = None
        _ACCESS_CACHE["exp_at"] = 0
    access = _get_access_token()
    return {
        "Authorization": f"Bearer {access}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ai-data-platform-mini/0.1",
    }


def _request(method: str, url: str, *, json_body=None, timeout=30):
    """
    统一请求封装：
    - 默认带 Bearer access
    - 若遇到 401，自动 refresh 再重试一次
    """
    r = requests.request(method, url, headers=_ls_headers(), json=json_body, timeout=timeout)
    if r.status_code == 401:
        r = requests.request(
            method, url, headers=_ls_headers(force_refresh=True), json=json_body, timeout=timeout
        )
    return r


def _get_max_ls_task_id(ls_base: str, project_id: int) -> int:
    """
    拿项目当前最大的 task id（用于兜底：导入后识别新任务）。
    如果网络很慢导致 ReadTimeout，就兜底返回 0，不让整个 job 失败。
    """
    url = f"{ls_base}/api/projects/{project_id}/tasks?ordering=-id&page_size=1"
    try:
        # 超时时间拉长一点，减少读超时
        r = _request("GET", url, timeout=60)
    except ReadTimeout:
        # 兜底：当作之前没有任务，从 0 开始
        return 0
    except RequestException as e:
        # 其它网络类错误就直接抛给上层，让 job 失败并记录 message
        raise RuntimeError(f"get max task id failed: {e}")

    if not r.ok:
        _raise_with_detail(r, "get max task id failed")
    data = r.json()
    if isinstance(data, dict) and data.get("results"):
        return int(data["results"][0]["id"])
    return 0


def _list_new_tasks(ls_base: str, project_id: int, after_id: int, limit: int):
    """
    兜底方案：拉取最新任务并取 id > after_id 的那些。
    如果这里 ReadTimeout，就返回空列表，让 job 仍然可以 success（只是 imported_tasks 可能为 0）。
    """
    url = f"{ls_base}/api/projects/{project_id}/tasks?ordering=-id&page_size=1000"
    try:
        r = _request("GET", url, timeout=120)  # 拉长一点，最多等 2 分钟
    except ReadTimeout:
        # 兜底：就当暂时拿不到，返回空列表
        return []
    except RequestException as e:
        raise RuntimeError(f"list new tasks failed: {e}")

    if not r.ok:
        _raise_with_detail(r, "list new tasks failed")
    data = r.json()
    results = data["results"] if isinstance(data, dict) else data
    ids = [int(t["id"]) for t in results if int(t["id"]) > after_id]
    ids = sorted(ids)
    return ids[-limit:] if len(ids) > limit else ids

def _extract_created_task_ids(resp_json):
    # list: [{id:..}, ...]
    if isinstance(resp_json, list):
        return [int(t["id"]) for t in resp_json if isinstance(t, dict) and "id" in t]

    # dict: task_ids/ids/tasks
    if isinstance(resp_json, dict):
        for k in ("task_ids", "ids"):
            if k in resp_json and isinstance(resp_json[k], list):
                try:
                    return [int(x) for x in resp_json[k]]
                except Exception:
                    pass

        if "tasks" in resp_json and isinstance(resp_json["tasks"], list):
            return [int(t["id"]) for t in resp_json["tasks"] if isinstance(t, dict) and "id" in t]

    return []


def _wait_import_complete(ls_base: str, project_id: int, import_id: int):
    status_url = f"{ls_base}/api/projects/{project_id}/import/{import_id}"
    for _ in range(60):  # 最多约 120 秒
        s = _request("GET", status_url, timeout=30)
        if not s.ok:
            _raise_with_detail(s, "poll import status failed")
        st = s.json()
        state = (st.get("status") or st.get("state") or "").lower()
        if state in ("completed", "success", "finished"):
            return
        if state in ("failed", "error"):
            raise RuntimeError(f"LS import failed: {str(st)[:300]}")
        time.sleep(2)


@celery.task(name="import_dataset_to_ls")
def import_dataset_to_ls(job_id: int):
    DATABASE_URL = os.environ["DATABASE_URL"]
    LS_BASE_URL = _ls_base()
    LS_PROJECT_ID = _ls_project_id()

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    with Session(engine) as db:
        job = db.get(Job, job_id)
        if not job:
            return {"ok": False, "error": "job not found"}

        ds = db.get(Dataset, job.dataset_id)
        if not ds:
            job.status = "failed"
            job.message = "dataset not found"
            db.commit()
            return {"ok": False, "error": "dataset not found"}

        job.status = "running"
        db.commit()

        items = (ds.items_json or {}).get("items", [])
        if not items:
            job.status = "failed"
            job.message = "dataset has no items"
            db.commit()
            return {"ok": False, "error": "dataset has no items"}

        payload = [{"data": {"text": it["text"]}} for it in items]

        try:
            before_max_id = _get_max_ls_task_id(LS_BASE_URL, LS_PROJECT_ID)

            # import 接口有的环境会要求末尾 /
            import_urls = [
                f"{LS_BASE_URL}/api/projects/{LS_PROJECT_ID}/import",
                f"{LS_BASE_URL}/api/projects/{LS_PROJECT_ID}/import/",
            ]

            last_err = None
            r = None

            for u in import_urls:
                r = _request("POST", u, json_body=payload, timeout=120)
                # 404 就换一个路径再试
                if r is not None and r.status_code == 404:
                    last_err = r
                    continue
                break

            # 两个 URL 都不行 或者返回非 2xx
            if r is None or not r.ok:
                if r is not None:
                    _raise_with_detail(r, "import tasks failed")
                if last_err is not None:
                    _raise_with_detail(last_err, "import tasks failed")
                raise RuntimeError("import tasks failed: no response")

            resp = r.json() if (r.text or "").strip() else {}
            created_ids = _extract_created_task_ids(resp)

            # 如果返回 {"import": import_id}，等它完成
            if (not created_ids) and isinstance(resp, dict) and "import" in resp:
                _wait_import_complete(LS_BASE_URL, LS_PROJECT_ID, int(resp["import"]))

            # 兜底：如果响应里拿不到 ids，就用 max_id 拉列表
            if not created_ids:
                created_ids = _list_new_tasks(
                    LS_BASE_URL, LS_PROJECT_ID, before_max_id, limit=len(items)
                )

            # 写回我们自己的 tasks 表
            for tid in created_ids:
                db.add(
                    Task(
                        dataset_id=ds.id,
                        ls_project_id=LS_PROJECT_ID,
                        ls_task_id=int(tid),
                        status="imported",
                    )
                )

            job.status = "success"
            job.message = f"imported {len(created_ids)} tasks"
            db.commit()

            return {
                "ok": True,
                "imported": len(created_ids),
                "ls_task_ids": created_ids[:10],
            }

        except Exception as e:
            job.status = "failed"
            job.message = str(e)[:500]
            db.commit()
            return {"ok": False, "error": job.message}

def _extract_label_from_ls_task(ls_task_json: dict) -> str | None:
    """
    尝试从 Label Studio task 详情里提取 Choices 标签（如 OK/NG）。
    兼容常见结构：task["annotations"][-1]["result"][...]["value"]["choices"]
    """
    anns = ls_task_json.get("annotations") or []
    if not anns:
        return None

    # 取最后一次标注（通常最后一个是最新）
    last = anns[-1] if isinstance(anns, list) else None
    if not isinstance(last, dict):
        return None

    results = last.get("result") or []
    if not isinstance(results, list):
        return None

    for r in results:
        if not isinstance(r, dict):
            continue
        v = r.get("value") or {}
        if isinstance(v, dict) and "choices" in v and isinstance(v["choices"], list) and v["choices"]:
            # 单选：取第一个
            return str(v["choices"][0])

    return None


@celery.task(name="export_dataset_from_ls")
def export_dataset_from_ls(job_id: int):
    DATABASE_URL = os.environ["DATABASE_URL"]
    LS_BASE_URL = _ls_base()
    LS_PROJECT_ID = _ls_project_id()

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    with Session(engine) as db:
        job = db.get(Job, job_id)
        if not job:
            return {"ok": False, "error": "job not found"}

        dataset_id = job.dataset_id
        job.status = "running"
        db.commit()

        try:
            # 找出这个 dataset 的所有已导入任务（有 ls_task_id 才能拉回）
            rows = db.execute(
                select(Task).where(Task.dataset_id == dataset_id, Task.ls_task_id.isnot(None))
            ).scalars().all()

            exported = 0

            for t in rows:
                url = f"{LS_BASE_URL}/api/tasks/{int(t.ls_task_id)}"
                r = _request("GET", url, timeout=30)
                if not r.ok:
                    _raise_with_detail(r, f"fetch ls task {t.ls_task_id} failed")

                ls_task = r.json() if r.text else {}
                anns = ls_task.get("annotations") or []

                # 没标注就跳过
                if not anns:
                    continue

                # 写回 annotation_json（你可以选择存最后一次或全部；这里存全部最安全）
                t.annotation_json = {"annotations": anns}

                # 尝试提取 OK/NG
                t.label = _extract_label_from_ls_task(ls_task)

                # 更新状态
                t.status = "labeled"
                exported += 1

            job.status = "success"
            job.message = f"exported {exported} labeled tasks"
            db.commit()
            return {"ok": True, "exported": exported}

        except Exception as e:
            job.status = "failed"
            job.message = str(e)[:500]
            db.commit()
            return {"ok": False, "error": job.message}