from typing import Optional
from fastapi import Header, HTTPException, status
from app.config import settings


def verify_admin_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not x_api_key or not settings.recovery_admin_api_key or x_api_key != settings.recovery_admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    return x_api_key
