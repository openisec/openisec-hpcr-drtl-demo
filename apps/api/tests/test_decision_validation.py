"""Decision / draft-decision request validation (target_date).

不正な日付が date.fromisoformat() まで届いて 500 になっていた問題の回帰テスト。
DB 不要の単体テスト(Pydantic モデルの検証のみ)。
"""
import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.messages import DecisionRequest, DraftDecisionUpdate


def _decision(**overrides):
    data = dict(
        decision="決定",
        ai_recommendation_action="adopted",
        reason="理由",
        target_date="2026-12-15",
    )
    data.update(overrides)
    return DecisionRequest(**data)


class TestDecisionRequestTargetDate:
    def test_valid_date_accepted(self):
        assert _decision().target_date == "2026-12-15"

    @pytest.mark.parametrize("bad", ["", "2026-13-45", "2026-02-30", "not-a-date", "12/15/2026"])
    def test_invalid_date_rejected_as_validation_error(self, bad):
        with pytest.raises(ValidationError):
            _decision(target_date=bad)


class TestDraftDecisionUpdateTargetDate:
    def test_valid_date_accepted(self):
        upd = DraftDecisionUpdate(target_date="2026-12-15")
        assert upd.target_date == "2026-12-15"

    @pytest.mark.parametrize("empty", [None, ""])
    def test_unset_target_allowed_and_normalized_to_none(self, empty):
        # 自動保存では「未選択」が空文字で送られてくる。
        assert DraftDecisionUpdate(target_date=empty).target_date is None

    @pytest.mark.parametrize("bad", ["2026-13-45", "2026-02-30", "not-a-date"])
    def test_invalid_date_rejected_as_validation_error(self, bad):
        with pytest.raises(ValidationError):
            DraftDecisionUpdate(target_date=bad)

    def test_all_fields_optional_for_partial_autosave(self):
        upd = DraftDecisionUpdate()
        assert upd.decision is None
        assert upd.ai_recommendation_action is None
        assert upd.reason is None
        assert upd.target_date is None

    def test_empty_action_treated_as_unselected(self):
        assert DraftDecisionUpdate(ai_recommendation_action="").ai_recommendation_action is None

    def test_invalid_action_still_rejected(self):
        with pytest.raises(ValidationError):
            DraftDecisionUpdate(ai_recommendation_action="bogus")
