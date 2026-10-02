"""FastAPI dependency-injection providers."""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request, status

from ai_core.common.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def require_api_key(c: Container = Depends(get_container), x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not any(hmac.compare_digest(x_api_key, k) for k in c.settings.api_key_set):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")
