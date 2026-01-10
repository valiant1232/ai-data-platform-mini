import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

JWT_SECRET = os.environ.get("JWT_SECRET", "dev_secret_change_me")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "120"))
ALGORITHM = "HS256"

def hash_password(p: str) -> str:
    return pwd_context.hash(p)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(subject: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError as e:
        raise ValueError("invalid token") from e
