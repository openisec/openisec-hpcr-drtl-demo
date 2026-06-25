import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db


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