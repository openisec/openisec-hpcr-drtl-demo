"""
ADR 001: schema="public" をハードコードするマイグレーションは、
provision_org_schema() がテナントスキーマ(org_*)向けに実行された際に
no-op となるよう、_schema() ヘルパー + ガード(if schema != "public": return)
を upgrade()/downgrade() の両方に持たなければならない。

このテストは、そのパターンが欠けている public 専用マイグレーションを
機械的に検出する。個々のマイグレーションのレビューに依存せず、
CI で自動的に落ちるようにするためのもの。
"""
import glob
import os
import re

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "migrations", "versions",
)

# Revisions that provision_org_schema() deliberately STAMPS PAST rather
# than upgrading through, when provisioning a tenant (org_*) schema (see
# app/core/provisioning.py). They may legitimately hardcode
# schema="public" with no internal guard, because the calling code never
# executes their upgrade()/downgrade() against a tenant schema in the
# first place. Any revision NOT in this set that hardcodes schema="public"
# WILL have its upgrade()/downgrade() executed by
# `alembic_command.upgrade(alembic_cfg, "head")` against tenant schemas,
# and therefore MUST guard itself per ADR 001.
STAMPED_PAST_EXEMPTIONS = {
    "0001",
    "765e0c1bd195",
    "a1b2c3d4e5f6",
    "b2c3d4e5f6a7",
    "c3d4e5f6a7b8",
}


def _function_body(content: str, func_name: str) -> str:
    """Extract a top-level function's source (crude but sufficient: from
    'def <func_name>(' to the next top-level 'def ' or end of file)."""
    match = re.search(
        rf"^def {func_name}\(.*?(?=^def |\Z)", content, re.S | re.M
    )
    return match.group(0) if match else ""


def _hardcodes_public_schema(func_body: str) -> bool:
    """True if the function body itself (not docstrings/comments)
    passes schema="public" (or ='public') as an actual argument."""
    return bool(re.search(r'schema\s*=\s*["\']public["\']', func_body))


def _revision_id(content: str) -> str | None:
    match = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', content, re.M)
    return match.group(1) if match else None


def _migrations_with_hardcoded_public_schema():
    """
    Migrations whose upgrade() or downgrade() body itself (excluding
    docstrings/comments) hardcodes schema="public", excluding revisions
    that provisioning.py deliberately stamps past instead of upgrading.
    """
    results = []
    for filepath in glob.glob(os.path.join(MIGRATIONS_DIR, "*.py")):
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        revision = _revision_id(content)
        if revision in STAMPED_PAST_EXEMPTIONS:
            continue

        upgrade_body = _function_body(content, "upgrade")
        downgrade_body = _function_body(content, "downgrade")

        if _hardcodes_public_schema(upgrade_body) or _hardcodes_public_schema(downgrade_body):
            results.append((filepath, content, upgrade_body, downgrade_body))

    return results


def test_public_only_migrations_have_schema_helper():
    """
    schema="public" を実際のコード(docstring等を除く)でハードコードして
    使用するマイグレーションは、_schema() ヘルパーを定義していなければ
    ならない(CLIの -x schema=<n> を読むため)。
    provision_org_schema() が明示的に stamp() で読み飛ばす例外リビジョンは
    対象外(STAMPED_PAST_EXEMPTIONS を参照)。
    """
    missing = []
    for filepath, content, _, _ in _migrations_with_hardcoded_public_schema():
        if "def _schema()" not in content:
            missing.append(os.path.basename(filepath))

    assert not missing, (
        "以下のマイグレーションは schema=\"public\" をハードコードしていますが "
        "_schema() ヘルパーがありません(ADR 001違反、provision_org_schema() "
        "実行時にテナントスキーマへ誤って適用される恐れがあります): "
        f"{missing}"
    )


def test_public_only_migrations_guard_upgrade_and_downgrade():
    """
    schema="public" をハードコードする箇所を持つ upgrade()/downgrade() は、
    冒頭で `if schema != "public": return` によるガードを持たなければ
    ならない。
    """
    guard_pattern = re.compile(r'if\s+schema\s*!=\s*["\']public["\']\s*:\s*\n\s*return')

    missing_guard = []
    for filepath, content, upgrade_body, downgrade_body in _migrations_with_hardcoded_public_schema():
        name = os.path.basename(filepath)
        if _hardcodes_public_schema(upgrade_body) and not guard_pattern.search(upgrade_body):
            missing_guard.append(f"{name}: upgrade()")
        if _hardcodes_public_schema(downgrade_body) and not guard_pattern.search(downgrade_body):
            missing_guard.append(f"{name}: downgrade()")

    assert not missing_guard, (
        "以下のマイグレーションは、schema=\"public\" をハードコードしている"
        "にもかかわらず ADR 001 のガード (`if schema != \"public\": return`) "
        "が見つかりませんでした。provision_org_schema() 経由で新規組織登録の"
        f"たびに public スキーマへ誤って再実行される恐れがあります: {missing_guard}"
    )
