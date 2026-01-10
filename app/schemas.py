from pydantic import BaseModel
from typing import Any, Optional

class DatasetCreateIn(BaseModel):
    name: str

class DatasetOut(BaseModel):
    id: int
    name: str
    created_by: str

class DatasetStatsOut(BaseModel):
    dataset_id: int
    total_tasks: int
    imported_tasks: int
    labeled_tasks: int
