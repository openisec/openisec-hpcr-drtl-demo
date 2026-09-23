"""
Tenant schema provisioning helpers.

Extracted out of app.api.v1.endpoints.auth so that both the
registration flow (auth.py) and the request-time self-healing check
(deps.get_org_db) can call provision_org_schema() without a circular
import (auth.py already imports several names from deps.py).
"""
import logging
import os

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command

from app.core.config import get_settings
from app.core.database import _validate_schema_name

logger = logging.getLogger("openisec.provisioning")
settings = get_settings()

ALEMBIC_INI_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "alembic.ini",
)


class _AlembicXArgs:
    def __init__(self, x):
        self.x = x


def provision_org_schema(schema: str) -> None:
    """
    Creates the tenant schema (if missing) and runs tenant-only
    migrations against it. Idempotent: safe to call again against a
    schema that is already fully provisioned (each step is a no-op in
    that case), which is what makes this usable both at registration
    time and as a request-time self-healing repair (see
    deps.get_org_db).

    Revisions 0001, 765e0c1bd195, a1b2c3d4e5f6, b2c3d4e5f6a7, and
    c3d4e5f6a7b8 are public-schema-only (hardcoded schema="public") and
    must never be executed against a tenant schema. We stamp past them,
    only actually running 0002 (tenant table creation) and everything
    from c3d4e5f6a7b8 onward that is properly schema-parameterized.
    """
    _validate_schema_name(schema)
    # 通常は settings.DATABASE_URL(.env)を使うが、テスト実行時は conftest.py が
    # TEST_DATABASE_URL_OVERRIDE を設定することで、Alembicの接続先だけをテスト用
    # PostgreSQL(localhost:5434)へ差し替えられるようにする。本番/開発環境では
    # このenv varは未設定のため、従来通り settings.DATABASE_URL が使われる。
    os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL_OVERRIDE") or settings.DATABASE_URL
    alembic_cfg = AlembicConfig(ALEMBIC_INI_PATH)
    alembic_cfg.cmd_opts = _AlembicXArgs([f"schema={schema}"])

    alembic_command.stamp(alembic_cfg, "0001")
    alembic_command.upgrade(alembic_cfg, "0002")
    alembic_command.stamp(alembic_cfg, "c3d4e5f6a7b8")
    alembic_command.upgrade(alembic_cfg, "head")
