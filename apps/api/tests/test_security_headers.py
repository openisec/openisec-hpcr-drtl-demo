"""API セキュリティヘッダーの回帰テスト(DB不要)。"""
from fastapi.testclient import TestClient

from app.main import app


def test_security_headers_present():
    r = TestClient(app).get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cross-Origin-Resource-Policy"] == "same-site"
