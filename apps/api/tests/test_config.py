from app.core.config import get_settings


def test_HPCRDTL_volume_limits():
    s = get_settings()
    assert s.HISTORY_MAX_CHARS == 300
    assert s.HISTORY_MAX_CHARS_MEDIUM == 400
    assert s.HISTORY_MAX_CHARS_LONG == 600
    assert s.PRO_MAX_ITEMS == 10
    assert s.PRO_ITEM_MAX_CHARS == 50
    assert s.CON_MAX_ITEMS == 10
    assert s.CON_ITEM_MAX_CHARS == 50
    assert s.RECOMMENDATION_MAX_CHARS == 300
    assert s.RECOMMENDATION_MAX_CHARS_MEDIUM == 400
    assert s.RECOMMENDATION_MAX_CHARS_LONG == 500


def test_query_length_thresholds():
    s = get_settings()
    assert s.QUERY_LENGTH_SHORT == 100
    assert s.QUERY_LENGTH_MEDIUM == 300


def test_input_guardrail():
    s = get_settings()
    assert s.INPUT_MAX_CHARS == 4000


def test_rate_limits():
    s = get_settings()
    assert s.AUTH_RATE_LIMIT_PER_MINUTE == 10
    assert s.API_RATE_LIMIT_PER_MINUTE == 60