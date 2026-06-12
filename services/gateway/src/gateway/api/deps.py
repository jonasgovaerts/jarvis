from __future__ import annotations

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.auth import credential_ok
from gateway.state import state


async def require_token(authorization: str = Header(default="")) -> None:
    credential = authorization.removeprefix("Bearer ").strip()
    if not await credential_ok(credential):
        raise HTTPException(status_code=401, detail="invalid or missing credentials")


async def db_session() -> AsyncSession:
    if state.session_factory is None:
        raise HTTPException(status_code=503, detail="database not ready")
    async with state.session_factory() as session:
        yield session
