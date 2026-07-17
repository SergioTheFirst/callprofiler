"""Tests for request/offer balance axis (B5)."""
from callprofiler.insight.features.base import Tier
from callprofiler.insight.features.linguistic import compute_request_balance


def _seg(speaker, text):
    return {"speaker": speaker, "text": text}


def test_other_asks_much_more_than_owner():
    segments = (
        [_seg("OTHER", "помоги мне пожалуйста")] * 5
        + [_seg("OWNER", "ладно, сделай")]
    )
    result = compute_request_balance(segments)
    assert "request_balance" in result
    feat = result["request_balance"]
    assert feat.value > 0.6  # (5-1)/6
    assert feat.support_n == 6
    assert feat.tier == Tier.ROBUST


def test_owner_asks_much_more_than_other():
    segments = (
        [_seg("OWNER", "помоги мне пожалуйста")] * 5
        + [_seg("OTHER", "хорошо сделаю")]
    )
    result = compute_request_balance(segments)
    assert result["request_balance"].value < -0.6


def test_balanced_requests_near_zero():
    segments = [
        _seg("OTHER", "подскажи пожалуйста"),
        _seg("OTHER", "посмотри там"),
        _seg("OWNER", "напомни мне"),
        _seg("OWNER", "отправь файл"),
    ]
    result = compute_request_balance(segments)
    assert abs(result["request_balance"].value) < 0.01


def test_below_gate_no_feature():
    segments = [_seg("OTHER", "помоги"), _seg("OWNER", "сделай")]
    assert compute_request_balance(segments) == {}


def test_unknown_speaker_not_counted():
    segments = [
        _seg("UNKNOWN", "помоги помоги помоги помоги помоги"),
        _seg("OTHER", "прошу"),
        _seg("OTHER", "скинь"),
        _seg("OTHER", "пришли"),
        _seg("OWNER", "хорошо"),
    ]
    result = compute_request_balance(segments)
    # 5 UNKNOWN-хитов не должны попасть ни в одну корзину — support_n=3, не 8
    assert result["request_balance"].support_n == 3


def test_multi_word_phrase_matches():
    segments = [
        _seg("OTHER", "мог бы ты помочь"),
        _seg("OTHER", "могла бы она заехать"),
        _seg("OTHER", "прошу тебя"),
        _seg("OWNER", "ладно"),
    ]
    result = compute_request_balance(segments)
    assert result["request_balance"].support_n == 3


def test_empty_segments_no_feature():
    assert compute_request_balance([]) == {}
