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
_issuer: str = ""  # exact issuer per the discovery document (incl. trailing /)
_jwks_lock = asyncio.Lock()


async def _jwks() -> tuple[pyjwt.PyJWKClient, str]:
    """JWKS client + exact issuer from OIDC discovery, cached per process."""
    global _jwks_client, _issuer
    if _jwks_client is None:
        async with _jwks_lock:
            if _jwks_client is None:
                base = settings().oidc_issuer.rstrip("/")
                discovery = f"{base}/.well-known/openid-configuration"

                def fetch() -> tuple[pyjwt.PyJWKClient, str]:
                    import json
                    import urllib.request

                    with urllib.request.urlopen(discovery, timeout=10) as response:  # noqa: S310
                        doc = json.load(response)
                    client = pyjwt.PyJWKClient(doc["jwks_uri"], cache_keys=True, lifespan=3600)
                    # Tokens carry `iss` exactly as discovery declares it
                    # (authentik includes a trailing slash) — never normalize.
                    return client, doc["issuer"]

                _jwks_client, _issuer = await asyncio.to_thread(fetch)
    return _jwks_client, _issuer


async def _valid_oidc_jwt(token: str) -> bool:
    cfg = settings()
    try:
        client, issuer = await _jwks()
        key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
        pyjwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=cfg.oidc_client_id,
            issuer=issuer,
        )
    except pyjwt.PyJWTError as exc:
        log.warning("JWT rejected: %s", exc)
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
