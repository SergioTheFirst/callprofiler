"""Tests for tempo/rhythm features (B1)."""
import statistics

from callprofiler.insight.features.base import Tier
from callprofiler.insight.features.tempo import compute_tempo


def _seg(call_id, speaker, text, start_ms, end_ms):
    return {"call_id": call_id, "speaker": speaker, "text": text,
            "start_ms": start_ms, "end_ms": end_ms}


def test_tempo_cps_exact_value():
    # 2 сегмента по 5 символов, по 1 сек каждый -> 10 символов / 2 сек = 5.0 cps
    segments = [
        _seg(1, "OTHER", "abcde", 0, 1000),
        _seg(1, "OTHER", "fghij", 2000, 3000),
    ]
    result = compute_tempo(segments)
    assert "tempo_cps" in result
    feat = result["tempo_cps"]
    assert abs(feat.value - 5.0) < 0.01
    assert feat.support_n == 2
    assert feat.tier == Tier.ROBUST


def test_tempo_cps_short_segments_dropped():
    segments = [
        _seg(1, "OTHER", "abcde", 0, 400),        # 400ms < 500ms -> отброшен
        _seg(1, "OTHER", "fghijklmno", 1000, 2000),  # 10 chars / 1s = 10 cps
    ]
    result = compute_tempo(segments)
    feat = result["tempo_cps"]
    assert abs(feat.value - 10.0) < 0.01
    assert feat.support_n == 1


def test_tempo_cps_owner_and_unknown_excluded():
    segments = [
        _seg(1, "OWNER", "должен быть исключён из подсчёта cps", 0, 1000),
        _seg(1, "UNKNOWN", "тоже исключён", 1000, 2000),
        _seg(1, "OTHER", "abcde", 2000, 3000),  # единственный участник
    ]
    result = compute_tempo(segments)
    feat = result["tempo_cps"]
    assert feat.support_n == 1
    assert abs(feat.value - 5.0) < 0.01


def test_tempo_no_timestamps_no_feature():
    segments = [{"call_id": 1, "speaker": "OTHER", "text": "без таймстампов"}]
    result = compute_tempo(segments)
    assert "tempo_cps" not in result
    assert "reply_latency_ms" not in result
    assert result == {}


def test_tempo_empty_segments():
    assert compute_tempo([]) == {}


def test_reply_latency_median_of_pairs():
    segments = [
        _seg(1, "OWNER", "вопрос", 0, 1000),
        _seg(1, "OTHER", "ответ", 1500, 2000),   # gap=500
        _seg(1, "OWNER", "ещё вопрос", 3000, 4000),
        _seg(1, "OTHER", "ещё ответ", 4300, 4900),  # gap=300
    ]
    result = compute_tempo(segments)
    assert "reply_latency_ms" in result
    feat = result["reply_latency_ms"]
    assert feat.value == statistics.median([500, 300])
    assert feat.support_n == 2


def test_reply_latency_ignores_unknown_between_pair():
    segments = [
        _seg(1, "OWNER", "вопрос", 0, 1000),
        _seg(1, "UNKNOWN", "перебивание", 1200, 1400),  # рвёт смежность OWNER->OTHER
        _seg(1, "OTHER", "ответ", 1500, 2000),
    ]
    result = compute_tempo(segments)
    assert "reply_latency_ms" not in result  # нет смежной пары OWNER->OTHER


def test_reply_latency_gap_out_of_range_dropped():
    segments = [
        _seg(1, "OWNER", "вопрос", 0, 1000),
        _seg(1, "OTHER", "перебил", 900, 1200),      # gap=-100 <= 0 -> отброшен
        _seg(2, "OWNER", "другой звонок", 0, 1000),
        _seg(2, "OTHER", "ответ спустя вечность", 20000, 20500),  # gap=19000 >= 15000 -> отброшен
    ]
    result = compute_tempo(segments)
    assert "reply_latency_ms" not in result


def test_reply_latency_cross_call_pair_ignored():
    segments = [
        _seg(1, "OWNER", "вопрос в звонке 1", 0, 1000),
        _seg(2, "OTHER", "ответ в звонке 2", 1200, 1800),  # другой call_id — не пара
    ]
    result = compute_tempo(segments)
    assert "reply_latency_ms" not in result


def test_tempo_accel_ratio_of_thirds():
    # 9 OTHER-сегментов одного звонка: первая треть медленная, последняя быстрая
    segments = []
    for i in range(3):  # первая треть (idx 0-2): 10 chars / 2s = 5 cps
        segments.append(_seg(1, "OTHER", "ab" * 5, i * 3000, i * 3000 + 2000))
    for i in range(3):  # средняя треть (idx 3-5) — не участвует в ratio
        segments.append(_seg(1, "OTHER", "middle", 20000 + i * 2000, 20000 + i * 2000 + 1000))
    for i in range(3):  # последняя треть (idx 6-8): 20 chars / 1s = 20 cps
        segments.append(_seg(1, "OTHER", "x" * 20, 40000 + i * 2000, 40000 + i * 2000 + 1000))

    result = compute_tempo(segments)
    assert "tempo_accel" in result
    feat = result["tempo_accel"]
    assert abs(feat.value - 4.0) < 0.01  # 20cps / 5cps
    assert feat.support_n == 1  # один квалифицирующийся звонок


def test_tempo_accel_skips_calls_with_few_other_segments():
    segments = [_seg(1, "OTHER", "abcde", i * 1000, i * 1000 + 600) for i in range(5)]  # только 5 < 6
    result = compute_tempo(segments)
    assert "tempo_accel" not in result


def test_tempo_accel_multiple_calls_uses_median():
    def call(call_id, ratio_factor):
        segs = []
        for i in range(3):
            segs.append(_seg(call_id, "OTHER", "ab" * 5, i * 3000, i * 3000 + 2000))  # 5cps
        for i in range(3):
            segs.append(_seg(call_id, "OTHER", "x" * 5, 20000, 20000 + 1000))
        last_chars = "x" * int(5 * ratio_factor)
        segs[-3:] = [_seg(call_id, "OTHER", last_chars, 20000 + i * 2000, 20000 + i * 2000 + 1000)
                     for i in range(3)]
        return segs

    segments = call(1, 2.0) + call(2, 4.0)
    result = compute_tempo(segments)
    assert result["tempo_accel"].support_n == 2


def test_tempo_cohort_fast_vs_slow_contacts_separate_by_one_sigma():
    """Когортный тест: «быстрые» vs «медленные» контакты разделяются по tempo_cps."""
    def fast_contact_segments(n=6):
        # много символов за короткое время
        return [_seg(1, "OTHER", "x" * 40, i * 2000, i * 2000 + 1000) for i in range(n)]

    def slow_contact_segments(n=6):
        # мало символов за долгое время
        return [_seg(1, "OTHER", "x" * 8, i * 4000, i * 4000 + 3000) for i in range(n)]

    fast_values = [compute_tempo(fast_contact_segments())["tempo_cps"].value for _ in range(5)]
    slow_values = [compute_tempo(slow_contact_segments())["tempo_cps"].value for _ in range(5)]

    pooled = fast_values + slow_values
    sigma = statistics.stdev(pooled)
    mean_diff = statistics.mean(fast_values) - statistics.mean(slow_values)
    assert mean_diff > sigma
