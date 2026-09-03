"""Automated integration test suite for Step 8 of The Inconvenient Vault.

Validates:
1. FastAPI Application REST endpoints (status, reset, sequential inputs, audit queries).
2. End-to-end 5-stage authentication traversal via HTTP REST routes.
3. Tamper lockdown and administrative override recovery via REST API.
4. Bidirectional WebSocket telemetry streaming on /ws/vault.
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


def test_full_sequential_authentication_via_rest_api(client: TestClient):
    """Verify complete 4-stage sequential authentication through REST endpoints."""
    # 0. Start Authentication
    res_start = client.post("/api/v1/vault/start")
    assert res_start.status_code == 200
    assert res_start.json()["data"]["state"] == VaultState.AWAITING_RFID.value

    # 1. Stage 1: RFID Scan (Seeded Operator 'OPERATOR_001')
    res_rfid = client.post("/api/v1/simulate/rfid", json={"card_uid": "E2806894"})
    assert res_rfid.status_code == 200
    assert res_rfid.json()["success"] is True
    assert res_rfid.json()["data"]["state"] == VaultState.AWAITING_FACE.value

    # 3. Stage 3: Facial Biometrics (Synthetic Subject 777)
    res_face = client.post(
        "/api/v1/simulate/face",
        json={"subject_seed": 777, "noise_level": 0.01},
    )
    assert res_face.status_code == 200
    assert res_face.json()["success"] is True
    assert res_face.json()["data"]["state"] == VaultState.AWAITING_KEYPAD_PIN.value

    # 4. Stage 4: Secret Password Key
    res_pwd = client.post(
        "/api/v1/auth/password",
        json={"pin": "VaultMasterKey#2026!"},
    )
    assert res_pwd.status_code == 200
    assert res_pwd.json()["success"] is True
    assert res_pwd.json()["data"]["state"] == VaultState.AWAITING_VOICE.value

    # 5. Stage 5: Voice Challenge Utterance (Speaker 1 + Challenge Phrase)
    res_voice = client.post(
        "/api/v1/simulate/voice",
        json={
            "speaker_seed": 1,
            "spoken_phrase": "OPEN SESAME OVERENGINEERED",
            "noise_level": 0.01,
        },
    )
    assert res_voice.status_code == 200
    assert res_voice.json()["success"] is True
    assert res_voice.json()["data"]["state"] == VaultState.UNLOCKED.value

    # Verify physical status endpoint reflects UNLOCKED solenoid state
    status_res = client.get("/api/v1/vault/status")
    assert status_res.status_code == 200
    assert status_res.json()["state"] == VaultState.UNLOCKED.value
    assert status_res.json()["is_locked"] is False
    assert status_res.json()["display"]["line1"] == "VAULT UNLOCKED"


# ============================================================================
# 3. Tamper Lockdown & Admin Override Recovery Tests
# ============================================================================


def test_tamper_and_admin_override_lockout_via_api(client: TestClient):
    """Verify tamper sensor actuation forces LOCKOUT, and admin override clears it."""
    # Trigger Tamper Event
    res_tamper = client.post(
        "/api/v1/simulate/tamper",
        json={"reason": "Chassis breach detected via optical sensor"},
    )
    assert res_tamper.status_code == 200
    assert res_tamper.json()["data"]["state"] == VaultState.LOCKOUT.value

    # Check status
    status_res = client.get("/api/v1/vault/status")
    assert status_res.json()["state"] == VaultState.LOCKOUT.value
    assert status_res.json()["is_alarm_active"] is True
    assert status_res.json()["is_locked"] is True

    # Attempt reset without admin key -> 403 Forbidden
    res_bad_reset = client.post("/api/v1/vault/reset", json={})
    assert res_bad_reset.status_code == 403

    # Attempt reset with invalid key -> 401 Unauthorized
    res_wrong_key = client.post("/api/v1/vault/reset", json={"admin_override_key": "WRONG_KEY"})
    assert res_wrong_key.status_code == 401

    # Clear lockout with valid administrator override key
    res_clear = client.post(
        "/api/v1/vault/reset", json={"admin_override_key": "ADMIN_RESET_9999"}
    )
    assert res_clear.status_code == 200
    assert res_clear.json()["data"]["state"] == VaultState.IDLE.value

    # Verify alarm disengaged
    final_status = client.get("/api/v1/vault/status")
    assert final_status.json()["state"] == VaultState.IDLE.value
    assert final_status.json()["is_alarm_active"] is False


# ============================================================================
# 4. Audit Log API & Cryptographic Hash Verification Tests
# ============================================================================


def test_audit_logs_query_and_integrity_via_api(client: TestClient):
    """Verify GET /api/v1/audit/logs returns hash-chained records with valid verification."""
    # Perform an action to populate audit logs
    client.post("/api/v1/vault/start")
    client.post("/api/v1/simulate/rfid", json={"card_uid": "E2806894"})

    res = client.get("/api/v1/audit/logs?limit=50")
    assert res.status_code == 200

    data = res.json()
    assert data["is_chain_valid"] is True
    assert data["integrity_error"] is None
    assert data["total_records"] >= 2
    assert len(data["logs"]) >= 2

    # Verify log attributes
    first_log = data["logs"][0]
    assert "entry_hash" in first_log
    assert "previous_hash" in first_log
    assert len(first_log["entry_hash"]) == 64


# ============================================================================
# 5. Real-Time WebSocket Telemetry Streaming Tests
# ============================================================================


def test_websocket_stream_receives_state_transitions(client: TestClient):
    """Verify WebSocket hub streams initial state, ping/pong, and transition broadcasts."""
    with client.websocket_connect("/ws/vault") as ws:
        # 1. Receive initial status upon connect
        initial_msg = ws.receive_json()
        assert initial_msg["event"] == "INITIAL_STATE"
        assert initial_msg["data"]["state"] == VaultState.IDLE.value

        # 2. Ping-pong test
        ws.send_text("ping")
        pong_msg = ws.receive_json()
        assert pong_msg["event"] == "PONG"

        # 3. Trigger state transition via REST and assert WebSocket broadcast
        client.post("/api/v1/vault/start")

        # Receive broadcasted STATE_CHANGE event
        broadcast_msg = ws.receive_json()
        assert broadcast_msg["event"] == "STATE_CHANGE"
        assert broadcast_msg["data"]["current_state"] == VaultState.AWAITING_RFID.value


if __name__ == "__main__":
    import sys

    print("Running Step 8 unit tests directly via pytest...")
    sys.exit(pytest.main(["-v", __file__]))
