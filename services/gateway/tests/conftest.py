import os

import pytest

# Configure BEFORE gateway.config is imported anywhere.
os.environ.setdefault("FAKE_K8S", "true")
os.environ["NATS_URL"] = ""  # skip NATS entirely; degrade path has its own guard
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test-gateway.db")
os.environ.setdefault("JARVIS_TOKEN", "")


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    for f in ("test-gateway.db",):
        if os.path.exists(f):
            os.remove(f)
