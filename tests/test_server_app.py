from __future__ import annotations

from fastapi.testclient import TestClient

from kis_cli.server.app import create_app
from kis_cli.server.jobs import JobQueue


def _instant_queue() -> JobQueue:
    return JobQueue(runner=lambda job: {"fetched": 1, "stored": 1, "market": "NASDAQ"})


def test_health() -> None:
    with TestClient(create_app(queue=_instant_queue())) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_create_and_get_job() -> None:
    queue = _instant_queue()
    with TestClient(create_app(queue=queue)) as client:
        response = client.post(
            "/jobs",
            json={"symbol": "NVDA", "interval": "1d", "start": "2024-01-01"},
        )
        assert response.status_code == 201
        created = response.json()
        assert created["status"] == "pending"
        assert created["symbol"] == "NVDA"

        queue.join()  # wait for the worker to finish

        fetched = client.get(f"/jobs/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "succeeded"


def test_get_missing_job_returns_404() -> None:
    with TestClient(create_app(queue=_instant_queue())) as client:
        assert client.get("/jobs/does-not-exist").status_code == 404


def test_loopback_guard_rejects_non_loopback_host() -> None:
    from kis_cli.server.__main__ import _is_loopback

    assert _is_loopback("127.0.0.1")
    assert _is_loopback("localhost")
    assert _is_loopback("::1")
    assert not _is_loopback("0.0.0.0")
    assert not _is_loopback("192.168.1.10")


def test_list_jobs() -> None:
    queue = _instant_queue()
    with TestClient(create_app(queue=queue)) as client:
        client.post("/jobs", json={"symbol": "A", "interval": "1d", "start": "2024-01-01"})
        client.post("/jobs", json={"symbol": "B", "interval": "1d", "start": "2024-01-01"})
        queue.join()
        listed = client.get("/jobs").json()
        assert {j["symbol"] for j in listed} == {"A", "B"}
