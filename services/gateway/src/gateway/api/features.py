from __future__ import annotations

from fastapi import APIRouter, Depends

from gateway.api.deps import require_token
from gateway.config import settings
from jarvis_core.dto import Features

router = APIRouter(prefix="/api/features", dependencies=[Depends(require_token)])


@router.get("")
async def get_features() -> Features:
    return Features(mail=settings().mail_enabled)
