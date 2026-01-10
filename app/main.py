from fastapi import FastAPI, Depends
from sqlalchemy import text, create_engine
import os

from app.routers.auth import router as auth_router
from app.routers.datasets import router as datasets_router
from app.routers.jobs import router as jobs_router
from app.deps import get_current_user, require_role
from app.models import Base
from app.routers import tasks
from app.routers import annotator_tasks

app = FastAPI(title="AI Data Platform Mini")

app.include_router(annotator_tasks.router)
app.include_router(tasks.router)

DATABASE_URL = os.environ.get("DATABASE_URL")
REDIS_URL = os.environ.get("REDIS_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Phase 2: 自动建表（MVP，不用 Alembic）
Base.metadata.create_all(engine)

# 路由挂载（一定要在 app 创建之后）
app.include_router(auth_router)
app.include_router(datasets_router)
app.include_router(jobs_router)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok", "redis_url": REDIS_URL}


@app.get("/me")
def me(user=Depends(get_current_user)):
    return user


@app.get("/admin/ping")
def admin_ping(user=Depends(require_role("admin"))):
    return {"ok": True, "as": "admin", "user": user}


@app.get("/annotator/ping")
def annotator_ping(user=Depends(require_role("admin", "annotator"))):
    return {"ok": True, "as": "annotator", "user": user}