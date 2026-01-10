from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.auth import verify_password, create_access_token, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Phase 1：先用“内存用户表”跑通概念
# Phase 2 再迁移到 Postgres users 表
USERS = None

def get_users():
    global USERS
    if USERS is None:
        USERS = {
            "admin": {"password_hash": hash_password("admin123"), "role": "admin"},
            "ann": {"password_hash": hash_password("ann123"), "role": "annotator"},
        }
    return USERS

class LoginIn(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(body: LoginIn):
    u = get_users().get(body.username)
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(subject=body.username, role=u["role"])
    return {"access_token": token, "token_type": "bearer", "role": u["role"]}
