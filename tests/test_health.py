"""Smoke test -- verifies the app boots and the health endpoint responds.
Run with: pytest (after `pip install -r requirements.txt` and setting a
dummy GROQ_API_KEY so Settings validation doesn't complain)."""
import os

os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "docs" in response.json()


def test_synthetic_leads_and_batch_lookup():
    response = client.post("/api/v1/leads/synthetic?count=3")
    assert response.status_code == 201
    body = response.json()
    assert body["clean_count"] + body["rejected_count"] == body["total_rows"]

    batch_id = body["batch_id"]
    lookup = client.get(f"/api/v1/leads/{batch_id}")
    assert lookup.status_code == 200
    assert lookup.json()["batch_id"] == batch_id
