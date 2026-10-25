import os
import shutil
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="agentjerry-test-")
os.environ["AGENTJERRY_DATA_DIR"] = _tmp
os.environ["AGENTJERRY_SCHEDULER"] = "0"
os.environ["AGENTJERRY_SYNC_EXECUTION"] = "1"
os.environ["AGENTJERRY_STEP_PACING_MS"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c
    shutil.rmtree(_tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "priya@brightpath.example", "password": "demo1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}
