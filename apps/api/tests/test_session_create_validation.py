"""
セッション作成の入力検証。

DAST(ZAP)が decision_type_id に "string" のような値を送ったところ、UUID列との
比較で例外になり、POST /sessions が500エラーになった。UUIDとして不正な値は
入口(スキーマ)で422として拒否する。
"""
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.session import SessionCreate


@pytest.mark.parametrize("bad", ["string", "123", "not-a-uuid", "00000000-0000-0000-0000-00000000000g"])
def test_invalid_decision_type_id_is_rejected(bad):
    with pytest.raises(ValidationError):
        SessionCreate(title="t", decision_type_id=bad)


def test_valid_or_missing_decision_type_id_is_accepted():
    assert SessionCreate(title="t").decision_type_id is None
    assert SessionCreate(title="t", decision_type_id="").decision_type_id == ""
    value = str(uuid.uuid4())
    assert SessionCreate(title="t", decision_type_id=value).decision_type_id == value
