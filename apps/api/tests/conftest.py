import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db
from app.core.security import hash_password
from app.models.base import Base
from app.models.public_models import Organization, User, EmailVerificationToken


def override_get_db():
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None
    try:
        yield mock_session
    finally:
        pass


@pytest.fixture
def client():
    """FastAPI test client with DB override"""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_no_db_override():
    """FastAPI test client without DB override"""
    with TestClient(app) as c:
        yield c


# ============================================================
# 以下、Cookie移行の正常系テスト用(実PostgreSQL・Dockerコンテナ)
# ============================================================

TEST_DATABASE_URL = "postgresql+psycopg2://postgres:testpass@localhost:5434/openisec_test"

# provision_org_schema() (app/core/provisioning.py) runs Alembic directly against
# os.environ["DATABASE_URL"], bypassing the get_db dependency override used by
# client_with_db below. Without this, registration tests that create a new org
# would have Alembic try to migrate the .env DATABASE_URL (dev/prod) instead of
# this test container, and fail with 503. Setting this before any test runs
# routes provisioning to the same test PostgreSQL container.
os.environ["TEST_DATABASE_URL_OVERRIDE"] = TEST_DATABASE_URL


@pytest.fixture(scope="session")
def test_engine():
    """テスト用PostgreSQLへの接続。セッション全体で1回だけテーブル作成・削除。"""
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """テストごとにトランザクションを張り、終了後にロールバックしてデータを残さない。"""
    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_org(db_session):
    """テスト用の組織を1件作成。"""
    org = Organization(
        id=uuid.uuid4(),
        name="Test Org",
        domain=f"test-{uuid.uuid4()}.local",
        pg_schema=f"org_{uuid.uuid4().hex}",
    )
    db_session.add(org)
    db_session.commit()
    return org


@pytest.fixture
def test_user(db_session, test_org):
    """テスト用のログイン可能なユーザーを1件作成。パスワードは平文で 'TestPassword123!'。"""
    user = User(
        id=uuid.uuid4(),
        organization_id=test_org.id,
        email="test@example.com",
        password_hash=hash_password("TestPassword123!"),
        family_name="Test",
        given_name="User",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def client_with_db(db_session):
    """モックではなく実PostgreSQL(テスト用コンテナ)を使うTestClient。"""
    def override_get_db_real():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db_real
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_verification_token(db_session):
    """
    有効な仮登録トークンをDBに挿入し、生トークンを返すヘルパー。
    email/expires_in_minutes/consumedを指定してテストケースに応じた
    トークン状態(期限切れ・消費済み等)を作れる。
    """
    def _make(email="newuser@example.com", expires_in_minutes=30, consumed=False):
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        row = EmailVerificationToken(
            id=uuid.uuid4(),
            email=email,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
            consumed_at=datetime.now(timezone.utc) if consumed else None,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(row)
        db_session.commit()
        return raw_token
    return _make