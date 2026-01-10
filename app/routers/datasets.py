from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, select, func, update
from sqlalchemy.orm import Session
from datetime import datetime
import os

from app.models import Dataset, Task, Job
from app.schemas import DatasetCreateIn, DatasetOut, DatasetStatsOut
from app.deps import get_current_user, require_role

from app.celery_app import import_dataset_to_ls, export_dataset_from_ls  # 两个 celery task


router = APIRouter(prefix="/datasets", tags=["datasets"])

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


# ✅ 关键：get_db 必须放在所有 Depends(get_db) 之前
def get_db():
    with Session(engine) as session:
        yield session


def make_demo_items(n: int = 100):
    return [{"id": i, "text": f"demo text {i}"} for i in range(1, n + 1)]


# -----------------------------
# Phase 5：导出标注结果（触发异步 job）
# -----------------------------
@router.post("/{dataset_id}/export_from_ls")
def export_from_ls(
    dataset_id: int,
    user=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    job = Job(type="export_from_ls", status="queued", dataset_id=dataset_id, created_by=user["username"])
    db.add(job)
    db.commit()
    db.refresh(job)

    export_dataset_from_ls.delay(job.id)
    return {"job_id": job.id, "status": job.status}


@router.post("", response_model=DatasetOut)
def create_dataset(
    body: DatasetCreateIn,
    user=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    ds = Dataset(
        name=body.name,
        items_json={"items": make_demo_items(100)},
        created_by=user["username"],
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return {"id": ds.id, "name": ds.name, "created_by": ds.created_by}


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"id": ds.id, "name": ds.name, "created_by": ds.created_by}


@router.get("/{dataset_id}/stats", response_model=DatasetStatsOut)
def dataset_stats(dataset_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Task).where(Task.dataset_id == dataset_id)) or 0
    imported_ = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.dataset_id == dataset_id,
            Task.status.in_(["imported", "labeled"]),
        )
    ) or 0
    labeled = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.dataset_id == dataset_id,
            Task.status == "labeled",
        )
    ) or 0
    return {"dataset_id": dataset_id, "total_tasks": total, "imported_tasks": imported_, "labeled_tasks": labeled}


@router.post("/{dataset_id}/import_to_ls")
def import_to_ls(dataset_id: int, user=Depends(require_role("admin")), db: Session = Depends(get_db)):
    job = Job(type="import_to_ls", status="queued", dataset_id=dataset_id, created_by=user["username"])
    db.add(job)
    db.commit()
    db.refresh(job)

    import_dataset_to_ls.delay(job.id)
    return {"job_id": job.id, "status": job.status}


# -----------------------------
# Phase 4.5（加分项）：自动分配
# -----------------------------
@router.post("/{dataset_id}/auto_assign")
def auto_assign(
    dataset_id: int,
    username: str,
    count: int = 20,
    user=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    try:
        count = int(count)
    except Exception:
        raise HTTPException(status_code=400, detail="count must be int")
    count = max(1, min(count, 500))

    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    ids = db.execute(
        select(Task.id)
        .where(Task.dataset_id == dataset_id, Task.assigned_to.is_(None))
        .order_by(Task.id.asc())
        .limit(count)
    ).scalars().all()

    if not ids:
        return {"ok": True, "dataset_id": dataset_id, "assigned_to": username, "assigned": 0, "task_ids": []}

    now = datetime.utcnow()
    db.execute(
        update(Task)
        .where(Task.id.in_(ids))
        .values(assigned_to=username, assigned_at=now)
    )
    db.commit()

    return {
        "ok": True,
        "dataset_id": dataset_id,
        "assigned_to": username,
        "assigned": len(ids),
        "task_ids": ids[:50],
    }