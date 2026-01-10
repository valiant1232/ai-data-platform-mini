from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from datetime import datetime
import os

from app.models import Task
from app.deps import get_current_user, require_role

router = APIRouter(prefix="/tasks", tags=["tasks"])

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

def get_db():
    with Session(engine) as db:
        yield db

@router.post("/{task_id}/assign/{username}")
def assign_task(
    task_id: int,
    username: str,
    user=Depends(get_current_user),
    _=Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.assigned_to = username
    task.assigned_at = datetime.utcnow()
    db.commit()

    return {"ok": True, "task_id": task_id, "assigned_to": username}
