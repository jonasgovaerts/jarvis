from functools import lru_cache

from jarvis_core.settings import JarvisSettings


class GatewaySettings(JarvisSettings):
    service_name: str = "gateway"

    # "token": static bearer (single-user default). "oidc": the SPA runs the
    # authorization-code+PKCE flow against OIDC_ISSUER and sends the resulting
    # JWT; the static token keeps working for port-forward/API use.
    auth_mode: str = "token"
    oidc_issuer: str = ""  # e.g. https://authentik.jonasg.be/application/o/jarvis/
    oidc_client_id: str = "jarvis"

    # Static bearer token for the single-user dashboard; empty disables auth
    # (local dev only — in-cluster it always comes from a Secret).
    jarvis_token: str = ""

    # Serve board fixtures instead of watching the K8s API (frontend dev / demos).
    fake_k8s: bool = False

    workitem_namespace: str = "jarvis"

    database_url: str = "sqlite+aiosqlite:///./jarvis-gateway.db"

    # Chat model (LiteLLM logical name); base URL comes from JarvisSettings.
    chat_model: str = "claude-sonnet"

    # Mirrors the workspace deployment's MAIL_ENABLED — keep the two env
    # values in sync in deploy/. The UI hides mail surfaces when off.
    mail_enabled: bool = True


@lru_cache
def settings() -> GatewaySettings:
    return GatewaySettings()
