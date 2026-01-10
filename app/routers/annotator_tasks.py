from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.models import Task
from app.deps import get_current_user

router = APIRouter(prefix="/annotator", tags=["annotator"])

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def get_db():
    with Session(engine) as db:
        yield db


def _get_username(user) -> str:
    """
    兼容两种 get_current_user 返回：
    - dict: {"username": "...", "role": "..."}
    - 对象: user.username
    """
    if isinstance(user, dict):
        u = (user.get("username") or "").strip()
    else:
        u = (getattr(user, "username", "") or "").strip()

    if not u:
        raise HTTPException(status_code=401, detail="Invalid user in token")
    return u


@router.get("/tasks")
def list_my_tasks(
    dataset_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    annotator/admin 都能用，但永远只看自己的 assigned_to
    """
    me = _get_username(user)

    stmt = select(Task).where(Task.assigned_to == me)

    if dataset_id is not None:
        stmt = stmt.where(Task.dataset_id == dataset_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)

    stmt = stmt.limit(min(int(limit), 200))
    rows = db.execute(stmt).scalars().all()

    return {
        "count": len(rows),
        "items": [
            {
                "id": t.id,
                "dataset_id": t.dataset_id,
                "ls_project_id": t.ls_project_id,
                "ls_task_id": t.ls_task_id,
                "status": t.status,
                "assigned_to": t.assigned_to,
                "assigned_at": t.assigned_at.isoformat() if getattr(t, "assigned_at", None) else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
    }


@router.get("/stats")
def my_stats(
    dataset_id: Optional[int] = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    方案A：annotator 只看自己的统计（assigned_to == 当前用户）
    可选 dataset_id 过滤
    """
    me = _get_username(user)

    # 1) assigned_total
    total_stmt = select(func.count()).select_from(Task).where(Task.assigned_to == me)
    if dataset_id is not None:
        total_stmt = total_stmt.where(Task.dataset_id == dataset_id)
    assigned_total = db.execute(total_stmt).scalar_one()

    # 2) assigned_imported（按 Phase2 口径：imported/labeled 都算“已导入”）
    imported_stmt = select(func.count()).select_from(Task).where(
        Task.assigned_to == me,
        Task.status.in_(("imported", "labeled")),
    )
    if dataset_id is not None:
        imported_stmt = imported_stmt.where(Task.dataset_id == dataset_id)
    assigned_imported = db.execute(imported_stmt).scalar_one()

    # 3) assigned_labeled
    labeled_stmt = select(func.count()).select_from(Task).where(
        Task.assigned_to == me,
        Task.status == "labeled",
    )
    if dataset_id is not None:
        labeled_stmt = labeled_stmt.where(Task.dataset_id == dataset_id)
    assigned_labeled = db.execute(labeled_stmt).scalar_one()

    return {
        "dataset_id": dataset_id,
        "assigned_total": int(assigned_total),
        "assigned_imported": int(assigned_imported),
        "assigned_labeled": int(assigned_labeled),
        "me": me,
    }