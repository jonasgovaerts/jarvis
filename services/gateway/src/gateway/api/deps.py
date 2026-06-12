from __future__ import annotations

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.config import settings
from gateway.state import state


async def require_token(
    authorization: str = Header(default=""),
    authentik_user: str = Header(default="", alias="X-authentik-username"),
) -> None:
    cfg = settings()
    if not cfg.jarvis_token and cfg.auth_mode != "forward-auth":
        return  # auth disabled (local dev)
    if cfg.jarvis_token and authorization == f"Bearer {cfg.jarvis_token}":
        return  # port-forward / API access keeps working in any mode
    if cfg.auth_mode == "forward-auth" and authentik_user:
        # Identity asserted by the traefik forwardAuth middleware (authentik
        # outpost). Reaching the pod bypassing the ingress is out of scope
        # for a single-user homelab.
        return
    raise HTTPException(status_code=401, detail="invalid or missing credentials")


async def db_session() -> AsyncSession:
    if state.session_factory is None:
        raise HTTPException(status_code=503, detail="database not ready")
    async with state.session_factory() as session:
        yield session
