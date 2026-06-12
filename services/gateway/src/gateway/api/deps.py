from __future__ import annotations

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.config import settings
from gateway.state import state


async def require_token(authorization: str = Header(default="")) -> None:
    expected = settings().jarvis_token
    if not expected:
        return  # auth disabled (local dev)
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid or missing token")


async def db_session() -> AsyncSession:
    if state.session_factory is None:
        raise HTTPException(status_code=503, detail="database not ready")
    async with state.session_factory() as session:
        yield session
