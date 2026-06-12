"""OIDC-mode credential validation with a locally signed RS256 JWT."""

import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from gateway import auth, config

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ISSUER = "https://authentik.jonasg.be/application/o/jarvis"


class FakeSigningKey:
    key = KEY.public_key()


class FakeJWKSClient:
    def get_signing_key_from_jwt(self, token):
        return FakeSigningKey()


def make_jwt(**overrides) -> str:
    claims = {
        "iss": ISSUER,
        "aud": "jarvis",
        "sub": "jonas",
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return pyjwt.encode(claims, KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def oidc_mode(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "jarvis")
    monkeypatch.setenv("JARVIS_TOKEN", "sekrit")
    monkeypatch.setattr(auth, "_jwks_client", FakeJWKSClient())
    config.settings.cache_clear()
    yield
    monkeypatch.setattr(auth, "_jwks_client", None)
    config.settings.cache_clear()


async def test_valid_jwt_accepted():
    assert await auth.credential_ok(make_jwt()) is True


async def test_static_token_still_works_in_oidc_mode():
    assert await auth.credential_ok("sekrit") is True


async def test_expired_jwt_rejected():
    assert await auth.credential_ok(make_jwt(exp=int(time.time()) - 10)) is False


async def test_wrong_audience_rejected():
    assert await auth.credential_ok(make_jwt(aud="other-app")) is False


async def test_wrong_issuer_rejected():
    assert await auth.credential_ok(make_jwt(iss="https://evil.example")) is False


async def test_garbage_and_empty_rejected():
    assert await auth.credential_ok("not-a-jwt") is False
    assert await auth.credential_ok("") is False
