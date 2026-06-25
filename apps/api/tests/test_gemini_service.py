import pytest
from app.services.gemini_service import _validate_output, _truncate_output


class TestValidateOutput:
    def test_valid_output(self):
        output = {
            "history": "test history",
            "pro": ["pro1", "pro2"],
            "con": ["con1", "con2"],
            "recommendation": "test recommendation",
            "risk_score": 10,
        }
        is_valid, reason = _validate_output(output)
        assert is_valid
        assert reason == ""

    def test_missing_required_field(self):
        output = {
            "history": "test history",
            "pro": ["pro1"],
            "con": ["con1"],
            "recommendation": "test recommendation",
            # risk_score missing
        }
        is_valid, reason = _validate_output(output)
        assert not is_valid
        assert "risk_score" in reason

    def test_risk_score_clamped(self):
        output = {
            "history": "h",
            "pro": [],
            "con": [],
            "recommendation": "r",
            "risk_score": 150,
        }
        _validate_output(output)
        assert output["risk_score"] == 100

    def test_risk_score_negative_clamped(self):
        output = {
            "history": "h",
            "pro": [],
            "con": [],
            "recommendation": "r",
            "risk_score": -10,
        }
        _validate_output(output)
        assert output["risk_score"] == 0

    def test_pro_must_be_list(self):
        output = {
            "history": "h",
            "pro": "not a list",
            "con": [],
            "recommendation": "r",
            "risk_score": 10,
        }
        is_valid, reason = _validate_output(output)
        assert not is_valid
        assert "pro" in reason


class TestTruncateOutput:
    def test_history_truncated(self):
        output = {
            "history": "x" * 400,
            "pro": [],
            "con": [],
            "recommendation": "r",
            "risk_score": 10,
        }
        result = _truncate_output(output)
        assert len(result["history"]) <= 303  # 300 + "..."

    def test_pro_items_truncated(self):
        output = {
            "history": "h",
            "pro": ["a" * 100] * 15,
            "con": [],
            "recommendation": "r",
            "risk_score": 10,
        }
        result = _truncate_output(output)
        assert len(result["pro"]) <= 10
        for item in result["pro"]:
            assert len(item) <= 50

    def test_recommendation_truncated(self):
        output = {
            "history": "h",
            "pro": [],
            "con": [],
            "recommendation": "r" * 400,
            "risk_score": 10,
        }
        result = _truncate_output(output)
        assert len(result["recommendation"]) <= 303  # 300 + "..."