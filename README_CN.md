# AI Data Platform Mini - Label Studio 数据中台

## 项目简介

一个轻量的「数据中台」后端，用来对接自建/远程的 Label Studio（HumanSignal/label-studio），实现：

- 数据集（Dataset）管理（MVP：生成 100 条 demo 文本）
- 将数据批量导入 Label Studio 项目（异步 job + Celery）
- 中台维护 tasks “影子索引”（用于统计、分发、权限视角）
- Admin 分配任务给标注员（单条 assign / 批量 auto_assign）
- Annotator 只能看自己被分配的任务与统计
- 从 Label Studio 导出标注结果回写到中台（闭环），更新 labeled 统计与 label（OK/NG）

---

## v0.31-prelabel

- 任务类型：文本二分类（OK / NG）
- 实现方式：中台后端调用 Ollama 推理，把预测结果写回 Label Studio 的 **Prediction**（标注员打开任务就能看到预测）
- 效果：标注员只需确认/修正 → 提升标注效率

### 不确定度与优先级定义

- `model_prob = confidence`
- `uncertainty_score = 1 - confidence`
- `priority = int(uncertainty_score * 1000)`

### 预标注与 Active Learning 闭环

- 后端异步打分：对未标注样本批量推理 + 计算不确定度 + 写回数据库 + 可写回 LS Prediction
- 提供高优先级任务列表：按 `priority desc` 返回（难样本优先）
- `auto_assign` 优先分配高不确定样本：实现“难样本优先标注”的闭环

---

## 技术栈

- FastAPI + Uvicorn
- Postgres（SQLAlchemy 2.0 / psycopg）
- Redis（Celery broker / backend）
- Celery（导入 / 导出 / 预标注 / 打分异步任务）
- requests / urllib（调用 Label Studio API / Ollama API）
- JWT（python-jose）+ bcrypt（passlib）

### 依赖版本

- fastapi==0.115.5
- uvicorn[standard]==0.32.0
- SQLAlchemy==2.0.36
- psycopg[binary]==3.2.3
- redis==5.2.0
- python-jose==3.3.0
- passlib[bcrypt]==1.7.4
- requests==2.32.3
- celery==5.4.0

---

## 架构与服务

使用 `docker compose` 一键启动四个服务：

- **db**: Postgres 16
- **redis**: Redis 7
- **api**: FastAPI（端口 8000）
- **worker**: Celery worker（执行 import/export/prelabel/score job）

---

## 目录结构

```text
.
├── docker-compose.yml
├── .env
├── .env.example
├── api/
│   ├── Dockerfile
│   └── requirements.txt
├── worker/
│   ├── Dockerfile
│   └── requirements.txt
└── app/
    ├── main.py
    ├── celery_app.py
    ├── models.py
    ├── deps.py
    ├── schemas.py
    └── routers/
        ├── auth.py
        ├── datasets.py
        ├── tasks.py
        ├── jobs.py
        └── annotator_tasks.py
```

---

## 配置

### 环境变量（.env）

#### 从模板复制

```bash
cp .env.example .env
```

#### 示例 `.env`（请按实际改）

```env
# Database
POSTGRES_DB=aiplatform
POSTGRES_USER=aiplatform
POSTGRES_PASSWORD=change_me_strong_password

# JWT
JWT_SECRET=change_me_super_secret
JWT_EXPIRE_MINUTES=120

# Label Studio
LS_BASE_URL=https://lancetops.com
LS_API_TOKEN=put_your_label_studio_token_here
LS_PROJECT_ID=1

# Ollama (Project 3)
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2:1b
OLLAMA_TIMEOUT=120
```

#### 字段说明

- `LS_BASE_URL`：Label Studio 服务地址（支持 https）
- `LS_PROJECT_ID`：你在 Label Studio 中手动创建的项目 ID
- `LS_API_TOKEN`：Label Studio 的 API Token（或 refresh token，按你当前实现）
- `OLLAMA_BASE_URL`：Ollama HTTP 服务地址  
  - Mac / Windows Docker：推荐 `http://host.docker.internal:11434`  
  - Linux Docker：需改成宿主机 IP（如 `http://172.17.0.1:11434` 或实际网卡 IP）
- `OLLAMA_MODEL`：要调用的模型名（例：`llama3.2:1b`）
- `OLLAMA_TIMEOUT`：推理超时时间（秒）

---

## “中台影子索引”是什么？

- Label Studio 是“标注真源”：任务、预测、标注都在 LS 里可视化管理
- 中台 DB 是“影子索引 / 缓存层”：保存 dataset / tasks / jobs 这些结构化信息，用于：
  - 权限视角（annotator 只能看到自己分配的任务）
  - 统计、分发、排序（priority / uncertainty）
  - 与 LS 的导入/导出/预标注/打分流程解耦（异步队列）

### 典型链路

- 导入：先把数据写入中台 dataset → 再导入 LS → 回写 `ls_task_id` 到中台 tasks
- 删除：如果要彻底删干净，一般需要“中台 DB 删除 + LS 任务删除”两边都做
- 本项目中：导入 / 导出 / 预标注 / 打分 / 分配 都通过中台 API 统一入口完成

---

## docker-compose.yml 关键点

- api 暴露 `8000:8000`
- db / redis 做了 healthcheck
- api / worker 通过环境变量拼接 `DATABASE_URL`、Redis broker/backend
- 已加入：`CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: "true"`（为 Celery 6 兼容做准备）

---

## 账号与认证

### 默认账号（MVP：内存用户表）

当前账号写死在 `app/routers/auth.py`（MVP 用内存 users 表跑通概念）：

- admin：`admin / admin123`（role=admin）
- annotator：`ann / ann123`（role=annotator）

### 登录接口

- `POST /auth/login`

#### 返回示例

```json
{"access_token":"...","token_type":"bearer","role":"admin"}
```

---

## 快速开始

### 1）启动服务

```bash
docker compose up -d --build
docker compose ps
```

### 2）健康检查与 OpenAPI

#### 健康检查

```bash
curl -s http://localhost:8000/health && echo
```

#### 查看 OpenAPI（确认 API 已加载）

```bash
curl -s http://localhost:8000/openapi.json | head -c 200 && echo
```

---

## 终端命令使用手册（复制即用）

### zsh 注意事项

你用的是 zsh：不要把 `# 注释` 写在同一条命令后面，否则会出现 `command not found: #`。

---

## Phase 0：登录拿 Token

### admin

```bash
TOKEN_ADMIN=$(curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "TOKEN_ADMIN len=${#TOKEN_ADMIN}"
```

### annotator（ann）

```bash
TOKEN_ANN=$(curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"ann","password":"ann123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "TOKEN_ANN len=${#TOKEN_ANN}"
```

### 验证身份

```bash
curl -s http://localhost:8000/me -H "Authorization: Bearer $TOKEN_ADMIN" && echo
curl -s http://localhost:8000/me -H "Authorization: Bearer $TOKEN_ANN" && echo
```

---

## Phase 2：创建数据集（生成 100 条 demo items）

### 创建 dataset

```bash
curl -s -X POST "http://localhost:8000/datasets" \
  -H "Authorization: Bearer $TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo-dataset"}' && echo
```

### 保存 dataset_id

你会拿到 `dataset_id`（例如 3），保存：

```bash
DATASET_ID=3
```

### 查看全局 stats

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

---

## Phase 3：导入到 Label Studio（异步 job）

### 触发导入

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/import_to_ls" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### 查询 job

返回 `job_id`（例如 4），查询 job：

```bash
JOB_ID=4
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### 成功示例

```json
{"status":"success","message":"imported 100 tasks"}
```

### 校验导入结果

此时 Label Studio 项目里应出现 100 条任务；中台侧 stats：

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

---

## Phase 4：任务分配（单条 / 批量）

### A）单条分配：POST /tasks/{task_id}/assign/{username}

先从 DB 拿一个 `task_id`：

```bash
TASK_ID=$(docker compose exec -T db psql -U aiplatform -d aiplatform -t -c \
"select id from tasks where dataset_id=$DATASET_ID order by id limit 1;" | tr -d '[:space:]')
echo "TASK_ID=$TASK_ID"
```

分配给 ann：

```bash
curl -s -X POST "http://localhost:8000/tasks/$TASK_ID/assign/ann" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### B）批量自动分配：POST /datasets/{id}/auto_assign?username=ann&count=20

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/auto_assign?username=ann&count=20" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### C）annotator 只看自己任务 / stats

#### 任务列表

```bash
curl -s "http://localhost:8000/annotator/tasks?dataset_id=$DATASET_ID&status=imported&limit=50" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo
```

#### 标注员 stats

```bash
curl -s "http://localhost:8000/annotator/stats?dataset_id=$DATASET_ID" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo
```

---

## Phase 5：导出标注结果（闭环）

### 1）在 Label Studio UI 标注

去 Label Studio UI 手动标注若干条（例如 4 条 OK/NG）。

### 2）中台触发导出

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/export_from_ls" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### 3）查询 job

拿到 `job_id`（例如 7），查询 job：

```bash
JOB_ID=7
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### 成功示例

```json
{"status":"success","message":"exported 4 labeled tasks"}
```

### 4）查看统计与 DB 验证

查看全局 stats 与个人 stats：

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

curl -s "http://localhost:8000/annotator/stats?dataset_id=$DATASET_ID" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo
```

（可选）从 DB 验证 labeled：

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select status, count(*) from tasks where dataset_id=$DATASET_ID group by status order by status;"
```

查看标注 label（OK/NG）：

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select id, ls_task_id, status, assigned_to, label from tasks where dataset_id=$DATASET_ID and status='labeled' limit 20;"
```

---

## Phase 6（Project 3.1）：AI 预标注（把预测写回 Label Studio）

### 前置：确保宿主机 Ollama 可用

宿主机启动（示例）：

```bash
ollama serve
```

拉取模型（示例）：

```bash
ollama pull llama3.2:1b
```

宿主机验证：

```bash
curl -s http://127.0.0.1:11434/api/tags | head -c 200 && echo
```

### 触发预标注（异步 job）

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/prelabel" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

返回示例：

```json
{"job_id":13,"status":"queued"}
```

### 查询 job

```bash
JOB_ID=13
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

成功示例（message 可能略不同）：

```json
{"status":"success","message":"prelabeled 100 tasks; wrote 100 predictions"}
```

### DB 验证（是否写入了 prelabel 字段）

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select count(*) as prelabeled from tasks where dataset_id=$DATASET_ID and prelabel_json is not null;"
```

查看前 10 条：

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select ls_task_id, prelabel_label, prelabel_score from tasks where dataset_id=$DATASET_ID order by id limit 10;"
```

---

## Phase 7（Project 3.2）：不确定度打分 + 优先级排序（Active Learning）

### 触发打分（异步 job）

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/score_uncertainty?limit=100&only_unlabeled=true" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

返回示例：

```json
{"job_id":11,"status":"queued"}
```

### 查询 job

```bash
JOB_ID=11
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### DB 验证（是否写入 model_prob / uncertainty_score / priority）

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select ls_task_id, prelabel_label, model_prob, uncertainty_score, priority
 from tasks
 where dataset_id=$DATASET_ID
 order by priority desc nulls last
 limit 10;"
```

### 获取高优先级任务列表（API）

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/priority_tasks?limit=10" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

返回字段包含：

- `task_id`
- `ls_task_id`
- `status`
- `assigned_to`
- `prelabel_label`
- `uncertainty_score`
- `priority`

---

## Phase 8（Project 3.2）：优先分配（auto_assign 按 priority desc）

把最不确定的样本优先分配给标注员（加分点）：

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/auto_assign?username=ann&count=5" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

DB 验证（看看最高 priority 的是否先 assigned_to=ann）：

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select ls_task_id, assigned_to, priority, uncertainty_score
 from tasks
 where dataset_id=$DATASET_ID
 order by priority desc nulls last
 limit 10;"
```

---

## Ollama 是怎么和中台连接的？

### 配置入口

`.env`：

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT`

### 调用逻辑

后端代码（通常在 `app/celery_app.py`）：

- 从环境变量读取 base_url / model / timeout
- Celery worker 调用 Ollama API：`POST /api/generate`

### Docker 里访问宿主机 Ollama

- Mac/Windows：`host.docker.internal` 由 Docker Desktop 提供
- Linux：需要改为宿主机可达 IP（否则 worker 会连不上）

---

## 权限边界（RBAC）

### admin 能做什么

- 登录拿 token
- 创建 dataset
- 导入 LS（import_to_ls）
- 分配任务（assign / auto_assign）
- 导出 LS 结果（export_from_ls）
- 预标注（prelabel）
- 打分排序（score_uncertainty / priority_tasks）
- 查 jobs、看全局 stats

### annotator 能做什么

- 登录拿 token
- 只看自己任务：`GET /annotator/tasks`
- 只看自己 stats：`GET /annotator/stats`
- 不能导入、不能分配、不能看别人的任务

---

## 常见问题排查

### 1）JSONDecodeError: Expecting value

说明 curl 没拿到 JSON（服务没起来 / 连接失败 / 返回空）。

```bash
curl -i http://localhost:8000/health
docker compose ps
docker compose logs --tail=200 api
```

### 2）LS 导入/导出慢

导出时 worker 可能会逐个拉 `/api/tasks/{id}`，100 条也能接受，但会慢一些；后续可以改成分页拉项目任务列表再过滤，或者并发请求。

### 3）worker 连不上 Ollama（常见于 Linux）

- Mac/Windows：保持 `OLLAMA_BASE_URL=http://host.docker.internal:11434`
- Linux：把 `host.docker.internal` 改为宿主机 IP 或网关 IP
- 验证 worker 到 Ollama 的连通性（示例）：

```bash
docker compose exec -T worker sh -lc 'python - << "PY"
import urllib.request
url="http://host.docker.internal:11434/api/tags"
print("GET", url)
print(urllib.request.urlopen(url, timeout=5).read()[:200].decode("utf-8","ignore"))
PY'
```
