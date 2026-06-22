from __future__ import annotations

from fastapi.testclient import TestClient

from finlabs_intelligence.api.app import app


def test_health_contract_is_safe_and_stable() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    serialized = response.text.casefold()
    assert "client_secret" not in serialized
    assert "app_secret" not in serialized


def test_openapi_exposes_stable_health_operation() -> None:
    schema = app.openapi()

    assert schema["paths"]["/api/health"]["get"]["operationId"] == "getHealth"
