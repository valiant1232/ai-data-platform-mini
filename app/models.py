from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Text

class Base(DeclarativeBase):
    pass

class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    items_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tasks: Mapped[List["Task"]] = relationship(back_populates="dataset", cascade="all,delete-orphan")

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    ls_project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ls_task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    annotation_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    dataset: Mapped["Dataset"] = relationship(back_populates="tasks")

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # import_to_ls
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")  # queued/running/success/failed
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

