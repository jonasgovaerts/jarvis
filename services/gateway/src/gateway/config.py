from functools import lru_cache

from jarvis_core.settings import JarvisSettings


class GatewaySettings(JarvisSettings):
    service_name: str = "gateway"

    # Static bearer token for the single-user dashboard; empty disables auth
    # (local dev only — in-cluster it always comes from a Secret).
    jarvis_token: str = ""

    # Serve board fixtures instead of watching the K8s API (frontend dev / demos).
    fake_k8s: bool = False

    workitem_namespace: str = "jarvis"


@lru_cache
def settings() -> GatewaySettings:
    return GatewaySettings()
