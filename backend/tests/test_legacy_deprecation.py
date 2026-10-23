"""Tests for legacy /api/v1/score deprecation middleware and health flag."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def has_deprecation_headers(response):
    return (
        response.headers.get("Deprecation") == "true"
        and response.headers.get("X-ICVER-Notice")
        == "legacy endpoint, use /api/v1/verify"
    )


def test_legacy_get_score_has_deprecation_headers(client):
    response = client.get("/api/v1/score/WRK-NOT-FOUND")
    assert response.status_code == 404
    assert has_deprecation_headers(response)


def test_legacy_post_score_has_deprecation_headers(client):
    response = client.post("/api/v1/score", json={})
    assert response.status_code == 422
    assert has_deprecation_headers(response)


def test_disabled_legacy_score_returns_410_for_post(client, monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_SCORE_ENABLED", False)
    response = client.post("/api/v1/score", json={})
    assert response.status_code == 410
    assert "removed" in response.json()["detail"].lower()
    assert "/api/v1/verify" in response.json()["detail"]
    assert has_deprecation_headers(response)


def test_disabled_legacy_score_returns_410_for_get(client, monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_SCORE_ENABLED", False)
    response = client.get("/api/v1/score/WRK-NOT-FOUND")
    assert response.status_code == 410
    assert has_deprecation_headers(response)


def test_other_paths_have_no_deprecation_headers(client):
    health = client.get("/health")
    verify = client.post("/api/v1/verify", json={})
    assert health.status_code == 200
    assert verify.status_code == 422
    assert "Deprecation" not in health.headers
    assert "Deprecation" not in verify.headers


def test_health_reports_legacy_score_enabled(client, monkeypatch):
    assert client.get("/health").json()["legacy_score_enabled"] is True
    monkeypatch.setattr(settings, "LEGACY_SCORE_ENABLED", False)
    assert client.get("/health").json()["legacy_score_enabled"] is False
