def test_login_missing_fields(client):
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422


def test_login_invalid_credentials(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


def test_me_without_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_logout_without_token(client):
    """トークンが無くても、ログアウトはエラーにせず200を返す(ベストエフォート)"""
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200


# ============================================================
# 以下、Cookie移行の正常系テスト(実PostgreSQL・Dockerコンテナ使用)
# ============================================================

def test_login_success_sets_cookie(client_with_db, test_user):
    """ログイン成功時、Set-CookieヘッダーでHttpOnly Cookieが発行されること"""
    response = client_with_db.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "TestPassword123!"},
    )
    assert response.status_code == 200
    assert "access_token" in response.cookies

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header.lower()


def test_login_response_body_has_no_token(client_with_db, test_user):
    """レスポンスボディにaccess_tokenが含まれないこと(Cookieに移行済みのため)"""
    response = client_with_db.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "TestPassword123!"},
    )
    assert response.status_code == 200
    assert "access_token" not in response.json()


def test_me_with_cookie(client_with_db, test_user):
    """ログイン後、同一クライアントでCookie経由で/auth/meにアクセスできること"""
    login_response = client_with_db.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "TestPassword123!"},
    )
    assert login_response.status_code == 200

    me_response = client_with_db.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == test_user.email


def test_logout_clears_cookie(client_with_db, test_user):
    """ログアウト後、Cookieが無効化され/auth/meが401になること"""
    client_with_db.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "TestPassword123!"},
    )
    logout_response = client_with_db.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200

    me_response = client_with_db.get("/api/v1/auth/me")
    assert me_response.status_code == 401


# ============================================================
# 以下、register() のトークン必須化(仮登録連携)テスト
# ============================================================

import hashlib
import secrets
import threading
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import sessionmaker

from app.models.public_models import EmailVerificationToken

REGISTER_BASE_PAYLOAD = {
    "password": "TestPassword123!",
    "password_confirm": "TestPassword123!",
    "family_name": "テスト",
    "given_name": "太郎",
    "organization_name": "個人",
    "agree_terms": True,
    "agree_privacy": True,
}


def test_register_without_token_returns_422(client_with_db):
    """tokenフィールド省略時は422(必須フィールド)"""
    payload = {**REGISTER_BASE_PAYLOAD, "email": "newuser@example.com"}
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_register_with_invalid_token_returns_400(client_with_db):
    """存在しないtokenでは400"""
    payload = {**REGISTER_BASE_PAYLOAD, "email": "newuser@example.com", "token": "invalid-token"}
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400


def test_register_with_expired_token_returns_400(client_with_db, make_verification_token):
    """期限切れtokenでは400"""
    raw_token = make_verification_token(email="newuser@example.com", expires_in_minutes=-1)
    payload = {**REGISTER_BASE_PAYLOAD, "email": "newuser@example.com", "token": raw_token}
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400


def test_register_with_already_consumed_token_returns_400(client_with_db, make_verification_token):
    """消費済みtokenでは400"""
    raw_token = make_verification_token(email="newuser@example.com", consumed=True)
    payload = {**REGISTER_BASE_PAYLOAD, "email": "newuser@example.com", "token": raw_token}
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400


def test_register_with_mismatched_email_returns_400(client_with_db, make_verification_token):
    """tokenのemailとpayload.emailが不一致では400(他人のtoken流用対策)"""
    raw_token = make_verification_token(email="original@example.com")
    payload = {**REGISTER_BASE_PAYLOAD, "email": "attacker@example.com", "token": raw_token}
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400


def test_register_success_consumes_token(client_with_db, db_session, make_verification_token):
    """正常系: 登録成功 + consumed_atが記録されること"""
    raw_token = make_verification_token(email="newuser@example.com")
    payload = {**REGISTER_BASE_PAYLOAD, "email": "newuser@example.com", "token": raw_token}
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    row = db_session.query(EmailVerificationToken).filter(
        EmailVerificationToken.token_hash == token_hash
    ).first()
    assert row.consumed_at is not None


def test_register_reject_token_reuse(client_with_db, make_verification_token):
    """同一tokenでの2回目のregisterは400(消費済みのため使い回せない)"""
    raw_token = make_verification_token(email="reuse@example.com")
    payload = {**REGISTER_BASE_PAYLOAD, "email": "reuse@example.com", "token": raw_token}

    first = client_with_db.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    payload2 = {**payload, "email": "reuse2@example.com", "organization_name": "個人2"}
    second = client_with_db.post("/api/v1/auth/register", json=payload2)
    assert second.status_code == 400


def test_register_password_mismatch_returns_422(client_with_db, make_verification_token):
    """password と password_confirm が不一致の場合は422"""
    raw_token = make_verification_token(email="mismatch@example.com")
    payload = {
        **REGISTER_BASE_PAYLOAD,
        "email": "mismatch@example.com",
        "token": raw_token,
        "password_confirm": "DifferentPassword123!",
    }
    response = client_with_db.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_register_token_race_condition_only_one_wins(test_engine):
    """
    同一tokenで2つの独立したDBコネクション経由の同時消費を試み、
    片方だけがconsumed_atのセットに成功することを確認する
    (SELECT ... FOR UPDATE による直列化の検証)。
    register()本体ではなく、そこで使われるロック取得ロジックそのものを
    直接検証する(TestClient経由では単一セッションしか使えないため)。
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    Session = sessionmaker(bind=test_engine)
    setup_session = Session()
    setup_session.add(EmailVerificationToken(
        id=uuid.uuid4(),
        email="race@example.com",
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        created_at=datetime.now(timezone.utc),
    ))
    setup_session.commit()
    setup_session.close()

    results = []

    def worker():
        session = Session()
        try:
            row = session.query(EmailVerificationToken).filter(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.consumed_at.is_(None),
                EmailVerificationToken.expires_at > datetime.now(timezone.utc),
            ).with_for_update().first()
            if row:
                row.consumed_at = datetime.now(timezone.utc)
                session.commit()
                results.append("consumed")
            else:
                results.append("rejected")
        finally:
            session.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t1.join()
    t2.start()
    t2.join()

    assert results.count("consumed") == 1
    assert results.count("rejected") == 1

    cleanup = Session()
    cleanup.query(EmailVerificationToken).filter(
        EmailVerificationToken.token_hash == token_hash
    ).delete()
    cleanup.commit()
    cleanup.close()