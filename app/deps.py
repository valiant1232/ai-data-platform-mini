from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.auth import decode_token

security = HTTPBearer(auto_error=False)

def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(security),
):
    if cred is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = cred.credentials
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"username": payload.get("sub"), "role": payload.get("role")}

def require_role(*roles: str):
    def _checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return _checker
