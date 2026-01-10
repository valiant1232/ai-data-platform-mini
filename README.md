# AI Data Platform Mini（Label Studio 数据中台 / 分发与回收闭环）

一个轻量的「数据中台」后端，用来对接自建/远程的 Label Studio（HumanSignal/label-studio），实现：
	•	数据集（Dataset）管理（MVP：生成 100 条 demo 文本）
	•	将数据批量导入 Label Studio 项目（异步 job + Celery）
	•	中台维护 tasks “影子索引”（用于统计、分发、权限视角）
	•	Admin 分配任务给标注员（单条 assign / 批量 auto_assign）
	•	Annotator 只能看自己被分配的任务与统计
	•	从 Label Studio 导出标注结果回写到中台（闭环），更新 labeled 统计与 label（OK/NG）

技术栈
	•	FastAPI + Uvicorn
	•	Postgres（SQLAlchemy 2.0 / psycopg）
	•	Redis（Celery broker / backend）
	•	Celery（导入 / 导出异步任务）
	•	requests（调用 Label Studio API）
	•	JWT（python-jose）+ bcrypt（passlib）

依赖版本：
	•	fastapi==0.115.5
	•	uvicorn[standard]==0.32.0
	•	SQLAlchemy==2.0.36
	•	psycopg[binary]==3.2.3
	•	redis==5.2.0
	•	python-jose==3.3.0
	•	passlib[bcrypt]==1.7.4
	•	requests==2.32.3
	•	celery==5.4.0

⸻

架构与服务

docker compose 一键启动四个服务：
	•	db: Postgres 16
	•	redis: Redis 7
	•	api: FastAPI（端口 8000）
	•	worker: Celery worker（执行 import/export job）

⸻

目录结构

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


⸻

环境变量（.env）

你当前的 .env（示例 / 建议放 .env.example）：

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

说明：
	•	LS_BASE_URL：Label Studio 服务地址（支持 https）
	•	LS_PROJECT_ID：你在 Label Studio 中手动创建的项目 ID
	•	LS_API_TOKEN：Label Studio 账号设置里生成的 API Token

⸻

docker-compose.yml

关键点说明：
	•	api 暴露 8000:8000
	•	db/redis 都做了 healthcheck
	•	api/worker 通过环境变量拼接 DATABASE_URL、Redis broker/backend
	•	你已加上：
	•	CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: "true"（为 Celery 6 兼容做准备）

⸻

默认账号（内存用户表）

当前账号写死在 app/routers/auth.py（MVP 用内存 users 表跑通概念）：
	•	admin：admin / admin123（role=admin）
	•	annotator：ann / ann123（role=annotator）

登录接口：
	•	POST /auth/login

返回：

{"access_token":"...","token_type":"bearer","role":"admin"}


⸻

快速开始

1）启动服务

在项目根目录：

docker compose up -d --build
docker compose ps

健康检查：

curl -s http://localhost:8000/health && echo

查看 OpenAPI（确认 API 已加载）：

curl -s http://localhost:8000/openapi.json | head -c 200 && echo


⸻

终端命令使用手册（推荐直接复制粘贴）

你用的是 zsh，记得：不要把 # 注释 写在同一条命令后面，否则会 command not found: #。

0）登录拿 Token

admin：

TOKEN_ADMIN=$(curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "TOKEN_ADMIN len=${#TOKEN_ADMIN}"

annotator（ann）：

TOKEN_ANN=$(curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"ann","password":"ann123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "TOKEN_ANN len=${#TOKEN_ANN}"

验证身份：

curl -s http://localhost:8000/me -H "Authorization: Bearer $TOKEN_ADMIN" && echo
curl -s http://localhost:8000/me -H "Authorization: Bearer $TOKEN_ANN" && echo


⸻

1）Phase 2：创建数据集（生成 100 条 demo items）

创建 dataset：

curl -s -X POST "http://localhost:8000/datasets" \
  -H "Authorization: Bearer $TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo-dataset"}' && echo

你会拿到 dataset_id，例如 3，保存：

DATASET_ID=3

看全局 stats：

curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo


⸻

2）Phase 3：导入到 Label Studio（异步 job）

触发导入：

curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/import_to_ls" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

返回 job_id，例如 4：

JOB_ID=4
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

成功示例：

{"status":"success","message":"imported 100 tasks"}

此时 Label Studio 项目里应出现 100 条任务；中台侧 stats：

curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo


⸻

3）Phase 4：任务分配（单条 / 批量）

A）单条分配：POST /tasks/{task_id}/assign/{username}

先从 DB 拿一个 task_id（取 dataset 里最小的一个）：

TASK_ID=$(docker compose exec -T db psql -U aiplatform -d aiplatform -t -c \
"select id from tasks where dataset_id=$DATASET_ID order by id limit 1;" | tr -d '[:space:]')
echo "TASK_ID=$TASK_ID"

分配给 ann：

curl -s -X POST "http://localhost:8000/tasks/$TASK_ID/assign/ann" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

B）批量自动分配：POST /datasets/{id}/auto_assign?username=ann&count=20

curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/auto_assign?username=ann&count=20" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

C）annotator 只看自己任务

任务列表：

curl -s "http://localhost:8000/annotator/tasks?dataset_id=$DATASET_ID&status=imported&limit=50" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo

annotator stats：

curl -s "http://localhost:8000/annotator/stats?dataset_id=$DATASET_ID" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo


⸻

4）Phase 5：导出标注结果（闭环）

1）去 Label Studio UI 手动标注若干条（例如 4 条 OK/NG）
2）中台触发导出：

curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/export_from_ls" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

拿到 job_id，例如 7，查询 job：

JOB_ID=7
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

成功示例：

{"status":"success","message":"exported 4 labeled tasks"}

查看全局 stats 与个人 stats：

curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

curl -s "http://localhost:8000/annotator/stats?dataset_id=$DATASET_ID" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo

（可选）从 DB 验证 labeled：

docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select status, count(*) from tasks where dataset_id=$DATASET_ID group by status order by status;"

以及查看标注 label（OK/NG）：

docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select id, ls_task_id, status, assigned_to, label from tasks where dataset_id=$DATASET_ID and status='labeled' limit 20;"


⸻

权限边界（RBAC）
	•	admin：
	•	登录拿 token
	•	创建 dataset
	•	导入 LS（import_to_ls）
	•	分配任务（assign / auto_assign）
	•	导出 LS 结果（export_from_ls）
	•	查 jobs、看全局 stats
	•	annotator：
	•	登录拿 token
	•	只看自己任务：GET /annotator/tasks
	•	只看自己 stats：GET /annotator/stats
	•	不能导入、不能分配、不能看别人的任务

⸻

常见问题排查

1）JSONDecodeError: Expecting value

说明 curl 没拿到 JSON（服务没起来/连接失败/返回空）。先做：

curl -i http://localhost:8000/health
docker compose ps
docker compose logs --tail=200 api

2）zsh: command not found: #

不要把 # 注释 写在一条命令后面，注释独立成一行。

3）LS 导入/导出慢

导出时 worker 可能会逐个拉 /api/tasks/{id}，100 条也能接受，但会慢一些；后续可以改成分页拉项目任务列表再过滤，或者并发请求。

⸻
