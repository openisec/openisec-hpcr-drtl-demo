"""
CTQP integration (C=Curiosity きっかけ / T=Thinking 事前の考え / Q=Questioning 解くべき問い).

DB・外部サービス不要の単体テスト。確認すること:
  - C/T は新規分析で必須(空・空白のみは不可)、1000文字上限
  - 下書き自動保存では C/T は任意(未指定=既存値維持)
  - C/T は Q と別の引数として AI分析(analyze_with_gemini)に渡される
  - SessionResponse は既存セッション(C/Tなし)でも生成できる(後方互換)
  - マイグレーションが ADR 001 に沿ったスキーマ引数付きで、単一headを保つ
"""
import glob
import inspect
import os
import re

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints import messages as messages_module
from app.api.v1.endpoints.messages import MessageRequest
from app.schemas.session import CTQP_FIELD_MAX, DraftQueryUpdate, SessionResponse

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "migrations", "versions",
)


def _valid_payload(**overrides):
    data = {
        "query": "AI時代に人間に必要な力とは",
        "curiosity": "AI時代に人間の役割はどう変わるのだろう？",
        "prior_thinking": "AIとの協業が重要になるのではないか",
    }
    data.update(overrides)
    return data


def test_message_request_accepts_valid_ctq():
    req = MessageRequest(**_valid_payload())
    assert req.curiosity.startswith("AI時代")
    assert req.prior_thinking.startswith("AIとの協業")


def test_message_request_strips_whitespace():
    req = MessageRequest(**_valid_payload(curiosity="  きっかけ  ", prior_thinking="\n考え\n"))
    assert req.curiosity == "きっかけ"
    assert req.prior_thinking == "考え"


@pytest.mark.parametrize("field", ["curiosity", "prior_thinking"])
def test_message_request_requires_c_and_t(field):
    payload = _valid_payload()
    del payload[field]
    with pytest.raises(ValidationError):
        MessageRequest(**payload)


@pytest.mark.parametrize("field", ["curiosity", "prior_thinking"])
@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_message_request_rejects_blank_c_and_t(field, blank):
    with pytest.raises(ValidationError):
        MessageRequest(**_valid_payload(**{field: blank}))


@pytest.mark.parametrize("field", ["curiosity", "prior_thinking"])
def test_message_request_enforces_max_length(field):
    MessageRequest(**_valid_payload(**{field: "あ" * CTQP_FIELD_MAX}))
    with pytest.raises(ValidationError):
        MessageRequest(**_valid_payload(**{field: "あ" * (CTQP_FIELD_MAX + 1)}))


def test_draft_update_ctqp_fields_are_optional():
    upd = DraftQueryUpdate(draft_query="途中のQ")
    assert upd.curiosity is None
    assert upd.prior_thinking is None


def test_draft_update_allows_empty_ctqp_but_enforces_max_length():
    upd = DraftQueryUpdate(draft_query="Q", curiosity="", prior_thinking="")
    assert upd.curiosity == ""
    with pytest.raises(ValidationError):
        DraftQueryUpdate(draft_query="Q", curiosity="あ" * (CTQP_FIELD_MAX + 1))


def test_session_response_backward_compatible_without_ctqp():
    resp = SessionResponse(
        id="s1",
        title="既存セッション",
        status="completed",
        created_at="2026-01-01T00:00:00Z",
    )
    assert resp.curiosity is None
    assert resp.prior_thinking is None


def test_session_response_carries_ctqp_values():
    resp = SessionResponse(
        id="s1",
        title="t",
        status="open",
        created_at="2026-01-01T00:00:00Z",
        curiosity="C",
        prior_thinking="T",
    )
    assert (resp.curiosity, resp.prior_thinking) == ("C", "T")


def test_ai_analysis_receives_c_t_and_q():
    """AI分析(Gemini呼び出し)に、C・T・Qがそれぞれ別の引数として渡されること。
    詳細な挙動は test_ctqp_analysis.py で検証する。"""
    source = inspect.getsource(messages_module.create_message)
    call = re.search(r"analyze_with_gemini\((.*?)\n\s*\)", source, re.S)
    assert call, "analyze_with_gemini call not found"
    call_args = call.group(1)
    assert "query=safe_query" in call_args
    assert "curiosity=safe_curiosity" in call_args
    assert "prior_thinking=safe_prior_thinking" in call_args


def test_ctqp_migration_is_schema_parameterized_and_nullable():
    path = glob.glob(os.path.join(MIGRATIONS_DIR, "*_add_ctqp_fields_to_sessions.py"))
    assert len(path) == 1
    content = open(path[0], encoding="utf-8").read()
    assert "_schema()" in content
    assert 'schema="public"' not in content
    assert content.count("nullable=True") == 2


def test_migration_history_has_single_head():
    revisions, downs = set(), set()
    for path in glob.glob(os.path.join(MIGRATIONS_DIR, "*.py")):
        content = open(path, encoding="utf-8").read()
        rev = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', content, re.M)
        down = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', content, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            downs.add(down.group(1))
    assert len(revisions - downs) == 1
