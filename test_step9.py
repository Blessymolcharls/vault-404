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


# ============================================================================
# 1. Static Asset Delivery & Root Page Serving Tests
# ============================================================================


def test_dashboard_root_serves_index_html(client: TestClient):
    """Verify GET / delivers the main operator dashboard index.html."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")

    html_content = response.text
    assert "The Inconvenient Vault" in html_content
    assert "oledLine1" in html_content
    assert "stepNodeIdle" in html_content
    assert "auditTableBody" in html_content
    assert "wsStatusIndicator" in html_content


def test_static_css_stylesheet_served(client: TestClient):
    """Verify GET /static/css/dashboard.css delivers valid CSS."""
    response = client.get("/static/css/dashboard.css")
    assert response.status_code == 200
    assert "text/css" in response.headers.get("content-type", "")

    css_content = response.text
    assert "--color-cyan" in css_content
    assert ".oled-container" in css_content
    assert ".lock-solenoid-graphic" in css_content


def test_static_js_client_script_served(client: TestClient):
    """Verify GET /static/js/vault_client.js delivers valid JavaScript."""
    response = client.get("/static/js/vault_client.js")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "")

    js_content = response.text
    assert "class VaultClient" in js_content
    assert "connectWebSocket" in js_content
    assert "updateHUD" in js_content


# ============================================================================
# 2. Simulated UI Client Authentication Flow Execution
# ============================================================================


def test_simulated_ui_client_e2e_authentication(client: TestClient):
    """Verify the exact sequence of REST requests triggered by the UI client leads to UNLOCKED."""
    # 1. Initial Status Check
    status1 = client.get("/api/v1/vault/status").json()
    assert status1["state"] == VaultState.IDLE.value

    # 2. UI Click "Start Chain"
    res_start = client.post("/api/v1/vault/start").json()
    assert res_start["success"] is True
    assert res_start["data"]["state"] == VaultState.AWAITING_RFID.value

    # 3. UI Click "Scan Authorized (E2806894)"
    res_rfid = client.post("/api/v1/simulate/rfid", json={"card_uid": "E2806894"}).json()
    assert res_rfid["success"] is True
    assert res_rfid["data"]["state"] == VaultState.AWAITING_FINGERPRINT.value

    # 4. UI Click "Scan Enrolled (Slot 1)"
    res_fp = client.post(
        "/api/v1/simulate/fingerprint",
        json={"finger_id": 1, "matched": True, "confidence": 0.98},
    ).json()
    assert res_fp["success"] is True
    assert res_fp["data"]["state"] == VaultState.AWAITING_FACE.value

    # 5. UI Click "Mock Operator (777)"
    res_face = client.post(
        "/api/v1/simulate/face",
        json={"subject_seed": 777, "noise_level": 0.01},
    ).json()
    assert res_face["success"] is True
    assert res_face["data"]["state"] == VaultState.AWAITING_PASSWORD.value

    # 6. UI Click "Inject Valid Key"
    res_pwd = client.post(
        "/api/v1/auth/password",
        json={"password": "VaultMasterKey#2026!"},
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
