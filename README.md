# AI Data Platform Mini - Label Studio Data Hub

## Project Overview

A lightweight "Data Hub" backend used to connect to a self-hosted/remote Label Studio (HumanSignal/label-studio), achieving the following:

- Dataset management (MVP: generate 100 demo text items)
- Batch import data into Label Studio projects (async job + Celery)
- The Data Hub maintains a "shadow index" of tasks (for statistics, distribution, and permission views)
- Admin assigns tasks to annotators (single `assign` / batch `auto_assign`)
- Annotators can only view their assigned tasks and personal statistics
- Export annotation results from Label Studio and write them back to the Data Hub (closed-loop), updating `labeled` statistics and labels (OK/NG)

---

## v0.31-prelabel

- **Task Type**: Text binary classification (OK / NG)
- **Implementation**: The Data Hub backend calls Ollama for inference and writes the predicted results back to the Label Studio **Prediction** (annotators will see the prediction upon opening the task).
- **Effect**: Annotators only need to confirm/correct → improves annotation efficiency.

### Uncertainty and Priority Definition

- `model_prob = confidence`
- `uncertainty_score = 1 - confidence`
- `priority = int(uncertainty_score * 1000)`

### Pre-labeling & Active Learning Closed-Loop

- **Backend asynchronous scoring**: Batch inference on unlabeled samples + uncertainty calculation + write back to database + optionally write back to LS Prediction.
- **Provide high-priority task lists**: Returned in `priority desc` order (hard samples first).
- **`auto_assign` prioritizes high-uncertainty samples**: Achieving the closed-loop of "prioritizing hard samples for annotation."

---

## Tech Stack

- FastAPI + Uvicorn
- Postgres (SQLAlchemy 2.0 / psycopg)
- Redis (Celery broker / backend)
- Celery (Import / export / prelabel / score async tasks)
- requests / urllib (Calling Label Studio API / Ollama API)
- JWT (python-jose) + bcrypt (passlib)

### Dependency Versions

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

## Architecture & Services

Use `docker compose` to start four services with one click:

- **db**: Postgres 16
- **redis**: Redis 7
- **api**: FastAPI (Port 8000)
- **worker**: Celery worker (Executes import/export/prelabel/score jobs)

---

## Directory Structure

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

## Configuration

### Environment Variables (.env)

#### Copy from template

```bash
cp .env.example .env
```

#### Example `.env` (Modify according to your actual setup)

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

#### Field Descriptions

- `LS_BASE_URL`: Label Studio service address (supports https)
- `LS_PROJECT_ID`: The Project ID you manually created in Label Studio
- `LS_API_TOKEN`: Label Studio API Token (or refresh token, depending on your implementation)
- `OLLAMA_BASE_URL`: Ollama HTTP service address  
  - Mac / Windows Docker: Recommended `http://host.docker.internal:11434`  
  - Linux Docker: Needs to be changed to the host IP (e.g., `http://172.17.0.1:11434` or actual NIC IP)
- `OLLAMA_MODEL`: Target model name (e.g., `llama3.2:1b`)
- `OLLAMA_TIMEOUT`: Inference timeout (seconds)

---

## What is the "Data Hub Shadow Index"?

- **Label Studio is the "Single Source of Truth"**: Tasks, predictions, and annotations are visually managed within LS.
- **Data Hub DB is the "Shadow Index / Cache Layer"**: It stores structural information like datasets / tasks / jobs, used for:
  - Permission viewing (annotators can only see tasks assigned to them).
  - Statistics, distribution, and sorting (priority / uncertainty).
  - Decoupling from LS import/export/prelabel/scoring workflows (async queues).

### Typical Data Flow

- **Import**: First, write data into the Data Hub dataset → then import into LS → write back `ls_task_id` to Data Hub tasks.
- **Deletion**: To completely delete, it generally requires both "Data Hub DB deletion + LS task deletion".
- **In this project**: Import / export / prelabel / score / assign are all handled through unified Data Hub API endpoints.

---

## Key Points in docker-compose.yml

- `api` exposes `8000:8000`
- `db` / `redis` have configured healthchecks
- `api` / `worker` construct the `DATABASE_URL` and Redis broker/backend via environment variables
- Added: `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: "true"` (Preparing for Celery 6 compatibility)

---

## Accounts & Authentication

### Default Accounts (MVP: In-memory user table)

Currently, accounts are hardcoded in `app/routers/auth.py` (MVP runs the concept using an in-memory users table):

- admin: `admin / admin123` (role=admin)
- annotator: `ann / ann123` (role=annotator)

### Login Endpoint

- `POST /auth/login`

#### Response Example

```json
{"access_token":"...","token_type":"bearer","role":"admin"}
```

---

## Quick Start

### 1) Start Services

```bash
docker compose up -d --build
docker compose ps
```

### 2) Health Check & OpenAPI

#### Health Check

```bash
curl -s http://localhost:8000/health && echo
```

#### View OpenAPI (Confirm API has loaded)

```bash
curl -s http://localhost:8000/openapi.json | head -c 200 && echo
```

---

## Terminal Command Guide (Copy & Paste to Use)

### zsh Notes

Since you are using zsh: Do not put `# comments` on the same line after a command, otherwise, you will get a `command not found: #` error.

---

## Phase 0: Login and Get Token

### Admin

```bash
TOKEN_ADMIN=$(curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "TOKEN_ADMIN len=${#TOKEN_ADMIN}"
```

### Annotator (ann)

```bash
TOKEN_ANN=$(curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"ann","password":"ann123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "TOKEN_ANN len=${#TOKEN_ANN}"
```

### Verify Identity

```bash
curl -s http://localhost:8000/me -H "Authorization: Bearer $TOKEN_ADMIN" && echo
curl -s http://localhost:8000/me -H "Authorization: Bearer $TOKEN_ANN" && echo
```

---

## Phase 2: Create Dataset (Generate 100 demo items)

### Create dataset

```bash
curl -s -X POST "http://localhost:8000/datasets" \
  -H "Authorization: Bearer $TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo-dataset"}' && echo
```

### Save dataset_id

You will receive a `dataset_id` (e.g., 3). Save it:

```bash
DATASET_ID=3
```

### View global stats

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

---

## Phase 3: Import to Label Studio (Async Job)

### Trigger import

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/import_to_ls" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### Query job

Returns a `job_id` (e.g., 4). Query the job:

```bash
JOB_ID=4
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### Success Example

```json
{"status":"success","message":"imported 100 tasks"}
```

### Verify Import Results

At this point, 100 tasks should appear in the Label Studio project. Data Hub side stats:

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

---

## Phase 4: Task Assignment (Single / Batch)

### A) Single Assignment: POST /tasks/{task_id}/assign/{username}

First, get a `task_id` from the DB:

```bash
TASK_ID=$(docker compose exec -T db psql -U aiplatform -d aiplatform -t -c \
"select id from tasks where dataset_id=$DATASET_ID order by id limit 1;" | tr -d '[:space:]')
echo "TASK_ID=$TASK_ID"
```

Assign to ann:

```bash
curl -s -X POST "http://localhost:8000/tasks/$TASK_ID/assign/ann" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### B) Batch Auto-Assignment: POST /datasets/{id}/auto_assign?username=ann&count=20

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/auto_assign?username=ann&count=20" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### C) Annotator Only Sees Own Tasks / Stats

#### Task List

```bash
curl -s "http://localhost:8000/annotator/tasks?dataset_id=$DATASET_ID&status=imported&limit=50" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo
```

#### Annotator Stats

```bash
curl -s "http://localhost:8000/annotator/stats?dataset_id=$DATASET_ID" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo
```

---

## Phase 5: Export Annotation Results (Closed-Loop)

### 1) Annotate in Label Studio UI

Go to the Label Studio UI and manually annotate a few items (e.g., 4 OK/NG tasks).

### 2) Trigger Export from Data Hub

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/export_from_ls" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### 3) Query job

Get the `job_id` (e.g., 7). Query the job:

```bash
JOB_ID=7
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### Success Example

```json
{"status":"success","message":"exported 4 labeled tasks"}
```

### 4) View Statistics and DB Verification

Check global stats and personal stats:

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/stats" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo

curl -s "http://localhost:8000/annotator/stats?dataset_id=$DATASET_ID" \
  -H "Authorization: Bearer $TOKEN_ANN" && echo
```

(Optional) Verify labeled status from the DB:

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select status, count(*) from tasks where dataset_id=$DATASET_ID group by status order by status;"
```

View annotation labels (OK/NG):

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select id, ls_task_id, status, assigned_to, label from tasks where dataset_id=$DATASET_ID and status='labeled' limit 20;"
```

---

## Phase 6 (Project 3.1): AI Pre-labeling (Write Predictions Back to Label Studio)

### Prerequisite: Ensure Host Ollama is Available

Start on host (Example):

```bash
ollama serve
```

Pull model (Example):

```bash
ollama pull llama3.2:1b
```

Verify on host:

```bash
curl -s http://127.0.0.1:11434/api/tags | head -c 200 && echo
```

### Trigger Pre-labeling (Async Job)

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/prelabel" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

Response Example:

```json
{"job_id":13,"status":"queued"}
```

### Query job

```bash
JOB_ID=13
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

Success Example (message may vary slightly):

```json
{"status":"success","message":"prelabeled 100 tasks; wrote 100 predictions"}
```

### DB Verification (Check if prelabel fields are written)

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select count(*) as prelabeled from tasks where dataset_id=$DATASET_ID and prelabel_json is not null;"
```

View the top 10 records:

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select ls_task_id, prelabel_label, prelabel_score from tasks where dataset_id=$DATASET_ID order by id limit 10;"
```

---

## Phase 7 (Project 3.2): Uncertainty Scoring + Priority Sorting (Active Learning)

### Trigger Scoring (Async Job)

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/score_uncertainty?limit=100&only_unlabeled=true" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

Response Example:

```json
{"job_id":11,"status":"queued"}
```

### Query job

```bash
JOB_ID=11
curl -s "http://localhost:8000/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

### DB Verification (Check if model_prob / uncertainty_score / priority are written)

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select ls_task_id, prelabel_label, model_prob, uncertainty_score, priority
 from tasks
 where dataset_id=$DATASET_ID
 order by priority desc nulls last
 limit 10;"
```

### Get High Priority Task List (API)

```bash
curl -s "http://localhost:8000/datasets/$DATASET_ID/priority_tasks?limit=10" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

Returned fields include:

- `task_id`
- `ls_task_id`
- `status`
- `assigned_to`
- `prelabel_label`
- `uncertainty_score`
- `priority`

---

## Phase 8 (Project 3.2): Priority Assignment (auto_assign by priority desc)

Prioritize assigning the most uncertain samples to annotators (Bonus Feature):

```bash
curl -s -X POST "http://localhost:8000/datasets/$DATASET_ID/auto_assign?username=ann&count=5" \
  -H "Authorization: Bearer $TOKEN_ADMIN" && echo
```

DB Verification (Check if the highest priority tasks are assigned to ann first):

```bash
docker compose exec -T db psql -U aiplatform -d aiplatform -c \
"select ls_task_id, assigned_to, priority, uncertainty_score
 from tasks
 where dataset_id=$DATASET_ID
 order by priority desc nulls last
 limit 10;"
```

---

## How Does Ollama Connect to the Data Hub?

### Configuration Entry

`.env`:

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT`

### Call Logic

Backend code (usually in `app/celery_app.py`):

- Reads base_url / model / timeout from environment variables
- Celery worker calls the Ollama API: `POST /api/generate`

### Accessing Host Ollama from Docker

- Mac/Windows: `host.docker.internal` is provided by Docker Desktop
- Linux: Needs to be changed to a host-reachable IP (otherwise the worker cannot connect)

---

## Permission Boundaries (RBAC)

### What Admin Can Do

- Login to get token
- Create dataset
- Import to LS (`import_to_ls`)
- Assign tasks (`assign` / `auto_assign`)
- Export LS results (`export_from_ls`)
- Pre-labeling (`prelabel`)
- Score and sort (`score_uncertainty` / `priority_tasks`)
- Query jobs, view global stats

### What Annotator Can Do

- Login to get token
- Only view own tasks: `GET /annotator/tasks`
- Only view own stats: `GET /annotator/stats`
- Cannot import, cannot assign, cannot view others' tasks

---

## Common Troubleshooting

### 1) JSONDecodeError: Expecting value

This means curl did not receive JSON (Service not running / connection failed / returned empty).

```bash
curl -i http://localhost:8000/health
docker compose ps
docker compose logs --tail=200 api
```

### 2) LS Import/Export is Slow

During export, the worker might fetch `/api/tasks/{id}` one by one. For 100 items, this is acceptable but somewhat slow. Future improvements could include paginating project task lists for filtering or using concurrent requests.

### 3) Worker Cannot Connect to Ollama (Common on Linux)

- Mac/Windows: Keep `OLLAMA_BASE_URL=http://host.docker.internal:11434`
- Linux: Change `host.docker.internal` to the host IP or gateway IP
- Verify worker connectivity to Ollama (Example):

```bash
docker compose exec -T worker sh -lc 'python - << "PY"
import urllib.request
url="http://host.docker.internal:11434/api/tags"
print("GET", url)
print(urllib.request.urlopen(url, timeout=5).read()[:200].decode("utf-8","ignore"))
PY'
```
