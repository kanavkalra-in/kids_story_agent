"""
Optional API key authentication.
When settings.api_key is configured, every request must include the header
    Authorization: Bearer <api_key>
When settings.api_key is None (default), authentication is disabled.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings
import hmac

_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """FastAPI dependency that enforces API key auth when configured."""
    if not settings.api_key:
        # Auth is disabled — allow all requests
        return

    if credentials is None or not hmac.compare_digest(credentials.credentials, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
