"""Credential validation for the two auth modes.

- "token": static bearer compared against JARVIS_TOKEN.
- "oidc": JWTs from authentik (authorization code + PKCE in the SPA),
  validated against the issuer's JWKS. The static token keeps working in
  oidc mode so port-forward/API access needs no browser flow.
"""

from __future__ import annotations

import asyncio
import logging

import jwt as pyjwt

from gateway.config import settings

log = logging.getLogger(__name__)

_jwks_client: pyjwt.PyJWKClient | None = None
_jwks_lock = asyncio.Lock()


async def _jwks() -> pyjwt.PyJWKClient:
    """JWKS client from OIDC discovery, cached for the process lifetime."""
    global _jwks_client
    if _jwks_client is None:
        async with _jwks_lock:
            if _jwks_client is None:
                issuer = settings().oidc_issuer.rstrip("/")
                discovery = f"{issuer}/.well-known/openid-configuration"

                def fetch() -> pyjwt.PyJWKClient:
                    import json
                    import urllib.request

                    with urllib.request.urlopen(discovery, timeout=10) as response:  # noqa: S310
                        jwks_uri = json.load(response)["jwks_uri"]
                    return pyjwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600)

                _jwks_client = await asyncio.to_thread(fetch)
    return _jwks_client


async def _valid_oidc_jwt(token: str) -> bool:
    cfg = settings()
    try:
        client = await _jwks()
        key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
        pyjwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=cfg.oidc_client_id,
            issuer=cfg.oidc_issuer.rstrip("/"),
        )
    except pyjwt.PyJWTError as exc:
        log.debug("JWT rejected: %s", exc)
        return False
    except Exception:
        log.exception("JWKS lookup failed")
        return False
    return True


async def credential_ok(credential: str) -> bool:
    """Shared by the REST dependency and the WebSocket endpoint."""
    cfg = settings()
    if not credential:
        return not cfg.jarvis_token and cfg.auth_mode != "oidc"  # local dev
    if cfg.jarvis_token and credential == cfg.jarvis_token:
        return True
    if cfg.auth_mode == "oidc" and credential.count(".") == 2:
        return await _valid_oidc_jwt(credential)
    return False
