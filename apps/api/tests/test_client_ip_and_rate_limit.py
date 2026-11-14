"""クライアントIP取得(X-Forwarded-For)とデフォルトレート制限の回帰テスト。

- X-Forwarded-For は右端から TRUSTED_PROXY_COUNT 番目を採用する。左端はクライアントが
  偽装できるため採用しない。
- FastAPI 0.139 + slowapi では default_limits が /api/v1 配下に効かなかった問題の回帰。
DB不要。
"""
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core import client_ip as client_ip_mod
from app.core import rate_limit as rl


def _req(xff=None, peer="10.0.0.9"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.fixture
def proxies(monkeypatch):
    def set_n(n):
        monkeypatch.setattr(client_ip_mod.settings, "TRUSTED_PROXY_COUNT", n)
    return set_n


class TestGetClientIp:
    def test_cloud_run_direct_uses_rightmost(self, proxies):
        proxies(1)
        assert client_ip_mod.get_client_ip(_req("203.0.113.7")) == "203.0.113.7"

    def test_spoofed_left_values_are_ignored(self, proxies):
        proxies(1)
        # クライアントが偽の値を前置しても、Cloud Runが追記した右端が採用される
        assert client_ip_mod.get_client_ip(_req("1.2.3.4, 203.0.113.7")) == "203.0.113.7"

    def test_behind_load_balancer_uses_second_from_right(self, proxies):
        proxies(2)
        assert client_ip_mod.get_client_ip(_req("6.6.6.6, 203.0.113.7, 35.191.0.1")) == "203.0.113.7"

    def test_no_header_falls_back_to_peer(self, proxies):
        proxies(1)
        assert client_ip_mod.get_client_ip(_req(None, peer="10.1.1.1")) == "10.1.1.1"

    def test_zero_proxies_ignores_header(self, proxies):
        proxies(0)
        assert client_ip_mod.get_client_ip(_req("203.0.113.7", peer="127.0.0.1")) == "127.0.0.1"

    def test_header_shorter_than_expected_falls_back_to_peer(self, proxies):
        proxies(2)
        assert client_ip_mod.get_client_ip(_req("203.0.113.7", peer="10.1.1.1")) == "10.1.1.1"

    def test_garbage_value_falls_back_to_peer(self, proxies):
        proxies(1)
        assert client_ip_mod.get_client_ip(_req("not-an-ip", peer="10.1.1.1")) == "10.1.1.1"

    def test_audit_module_uses_same_function(self):
        from app.core import audit
        assert audit.get_client_ip is client_ip_mod.get_client_ip


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rl.settings, "API_RATE_LIMIT_PER_MINUTE", 3)
    monkeypatch.setattr(client_ip_mod.settings, "TRUSTED_PROXY_COUNT", 1)
    rl.limiter.reset()
    inner = APIRouter()

    @inner.get("/ping")
    def ping():
        return {"ok": True}

    @inner.get("/other")
    def other():
        return {"ok": True}

    api = APIRouter()
    api.include_router(inner)
    app = FastAPI()
    # 本番(main.py)と同じ: include_router にデフォルト制限を依存関係で付ける
    app.include_router(api, prefix="/api/v1", dependencies=[Depends(rl.default_rate_limit)])
    yield TestClient(app)
    rl.limiter.reset()


def _codes(c, path, ip, n):
    return [c.get(path, headers={"X-Forwarded-For": ip}).status_code for _ in range(n)]


class TestDefaultRateLimit:
    def test_limit_applies_under_included_router(self, client):
        assert _codes(client, "/api/v1/ping", "203.0.113.1", 5) == [200, 200, 200, 429, 429]

    def test_429_has_retry_after(self, client):
        _codes(client, "/api/v1/ping", "203.0.113.2", 3)
        r = client.get("/api/v1/ping", headers={"X-Forwarded-For": "203.0.113.2"})
        assert r.status_code == 429 and r.headers["retry-after"] == "60"

    def test_other_clients_are_not_affected(self, client):
        _codes(client, "/api/v1/ping", "203.0.113.3", 5)
        assert _codes(client, "/api/v1/ping", "203.0.113.4", 3) == [200, 200, 200]

    def test_spoofing_left_value_does_not_bypass(self, client):
        codes = [
            client.get("/api/v1/ping", headers={"X-Forwarded-For": f"9.9.9.{i}, 203.0.113.5"}).status_code
            for i in range(5)
        ]
        assert codes == [200, 200, 200, 429, 429]

    def test_counted_per_route(self, client):
        _codes(client, "/api/v1/ping", "203.0.113.6", 5)
        assert _codes(client, "/api/v1/other", "203.0.113.6", 3) == [200, 200, 200]
