"""rename session status values: closed->completed, archived->closed (tenant-schema parameterized)

Revision ID: b6d4f8a2c1e7
Revises: 102e1cc9b8b4
Create Date: 2026-08-08

sessions.status の値の意味が英語表現と直感的に一致していなかったため、
以下の通りリネームする:
  - 旧 "closed"   (決定確定・完了) -> 新 "completed"
  - 旧 "archived" (利用者による終了操作) -> 新 "closed"

sessions はテナント側テーブルのため、f8a3c5e7d9b1 と同じ方式で schema
引数をそのまま使う(public実行時はテンプレートのpublic.sessions、
-x schema=org_xxx 実行時はそのテナントスキーマに対して適用される)。

順序に注意: 先に旧"closed"を"completed"へ、次に旧"archived"を"closed"へ
変換する。この順序であれば、2段目で書き込む新しい"closed"値と
1段目で読み込む旧"closed"値が衝突しない。

Run against public (default):
  alembic upgrade head

Run per existing org (このリビジョン単体を確実に当てる場合):
  alembic -x schema=org_<uuid_no_hyphens> upgrade head
"""
from alembic import op
import sqlalchemy as sa

revision = "b6d4f8a2c1e7"
down_revision = "102e1cc9b8b4"
branch_labels = None
depends_on = None


def _schema() -> str:
    """Read -x schema=<name> passed on CLI. Defaults to public."""
    from alembic import context  # local import avoids circular

    return context.get_x_argument(as_dictionary=True).get("schema", "public")


def upgrade() -> None:
    schema = _schema()
    op.execute(
        sa.text(f'UPDATE "{schema}".sessions SET status = \'completed\' WHERE status = \'closed\'')
    )
    op.execute(
        sa.text(f'UPDATE "{schema}".sessions SET status = \'closed\' WHERE status = \'archived\'')
    )


def downgrade() -> None:
    schema = _schema()
    op.execute(
        sa.text(f'UPDATE "{schema}".sessions SET status = \'archived\' WHERE status = \'closed\'')
    )
    op.execute(
        sa.text(f'UPDATE "{schema}".sessions SET status = \'closed\' WHERE status = \'completed\'')
    )
