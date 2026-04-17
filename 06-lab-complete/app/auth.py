"""API key authentication helpers."""
from __future__ import annotations

import hmac
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """
    FastAPI dependency that enforces X-API-Key.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include header: X-API-Key: <your-key>",
        )
    if not hmac.compare_digest(api_key, settings.agent_api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

