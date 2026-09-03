"""Automated integration test suite for Step 9 of The Inconvenient Vault.

Validates:
1. Static asset serving for HTML dashboard, CSS stylesheet, and JS client.
2. Root URL (GET /) rendering semantic index.html.
3. Client-side simulated workflow execution through REST and WebSocket channels.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.types import VaultState
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a TestClient configured with an in-memory SQLite database."""
    app = create_app()
    app.state.db_url = "sqlite+aiosqlite:///:memory:"
    with TestClient(app) as test_client:
        yield test_client


    assert res_fp["data"]["state"] == VaultState.AWAITING_FACE.value

    # 5. UI Click "Mock Operator (777)"
    res_face = client.post(
        "/api/v1/simulate/face",
        json={"subject_seed": 777, "noise_level": 0.01},
    ).json()
    assert res_face["success"] is True
    assert res_face["data"]["state"] == VaultState.AWAITING_KEYPAD_PIN.value

    # 6. UI Click "Inject Valid Key"
    res_pwd = client.post(
        "/api/v1/auth/password",
        json={"pin": "VaultMasterKey#2026!"},
    ).json()
    assert res_pwd["success"] is True
    assert res_pwd["data"]["state"] == VaultState.AWAITING_VOICE.value

    # 7. UI Click "Mock Voice Operator (Seed 1)"
    res_voice = client.post(
        "/api/v1/simulate/voice",
        json={
            "speaker_seed": 1,
            "spoken_phrase": "OPEN SESAME OVERENGINEERED",
            "noise_level": 0.01,
        },
    ).json()
    assert res_voice["success"] is True
    assert res_voice["data"]["state"] == VaultState.UNLOCKED.value

    # 8. UI Live Audit Trail Query
    audit_data = client.get("/api/v1/audit/logs?limit=50").json()
    assert audit_data["is_chain_valid"] is True
    assert audit_data["integrity_error"] is None
    assert audit_data["total_records"] >= 6


if __name__ == "__main__":
    import sys

    print("Running Step 9 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
