from __future__ import annotations

from fastapi import APIRouter

from gateway.config import settings
from jarvis_core.dto import Features

# Deliberately unauthenticated: the SPA needs the auth mode before it can
# decide whether to prompt for a token. Exposes feature booleans only.
router = APIRouter(prefix="/api/features")


@router.get("")
async def get_features() -> Features:
    cfg = settings()
    return Features(
        mail=cfg.mail_enabled,
        auth=cfg.auth_mode,
        oidc_issuer=cfg.oidc_issuer,
        oidc_client_id=cfg.oidc_client_id if cfg.auth_mode == "oidc" else "",
    )
