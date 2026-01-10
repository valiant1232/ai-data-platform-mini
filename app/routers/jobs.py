from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
import os

from app.models import Job
from app.deps import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

def get_db():
    with Session(engine) as db:
        yield db

@router.get("/{job_id}")
def get_job(job_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "dataset_id": job.dataset_id,
        "message": job.message,
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat(),
    }
