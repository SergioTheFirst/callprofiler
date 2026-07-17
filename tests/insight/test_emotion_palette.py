"""Tests for emotional palette lexicon features (B4)."""
from callprofiler.insight.features.base import Tier
from callprofiler.insight.features.emotion_palette import compute_emotion_palette


def _seg(text, speaker="OTHER"):
    return [{"speaker": speaker, "text": text}]


def test_anger_phrase_hits_only_anger():
    result = compute_emotion_palette(_seg("он меня реально бесит, сколько можно"))
    assert result["emo_anger"].value > 0
    assert result["emo_anger"].support_n == 1
    assert result["emo_anger"].tier == Tier.AFFECTIVE
    assert result["emo_anxiety"].value == 0.0
    assert result["emo_joy"].value == 0.0
    assert result["emo_contempt"].value == 0.0


def test_anxiety_phrase_hits_only_anxiety():
    result = compute_emotion_palette(_seg("мне очень страшно и я тревожусь"))
    assert result["emo_anxiety"].value > 0
    assert result["emo_anxiety"].support_n == 2  # страшно + тревожусь
    assert result["emo_anger"].value == 0.0


def test_joy_phrase_hits_only_joy():
    result = compute_emotion_palette(_seg("я так рад, это просто здорово"))
    assert result["emo_joy"].value > 0
    assert result["emo_joy"].support_n == 2  # рад + здорово
    assert result["emo_contempt"].value == 0.0


def test_contempt_phrase_hits_only_contempt():
    result = compute_emotion_palette(_seg("какой он жалкий и ничтожный тип"))
    assert result["emo_contempt"].value > 0
    assert result["emo_contempt"].support_n == 2  # жалкий + ничтожный
    assert result["emo_joy"].value == 0.0


def test_support_n_equals_hit_count_not_token_count():
    result = compute_emotion_palette(_seg("бесит бесит бесит спокойный текст без эмоций тут"))
    assert result["emo_anger"].support_n == 3


def test_exact_match_marker_blocks_prefix_false_positive():
    result = compute_emotion_palette(_seg("занимаюсь психологией много лет"))
    assert result["emo_anger"].value == 0.0
    assert result["emo_anger"].support_n == 0


def test_exact_match_marker_hits_on_exact_token():
    result = compute_emotion_palette(_seg("он вообще псих"))
    assert result["emo_anger"].support_n == 1


def test_owner_speech_filtered_out():
    segments = [
        {"speaker": "OWNER", "text": "бесит бесит бесит"},
        {"speaker": "OTHER", "text": "нормально всё, спокойно"},
    ]
    result = compute_emotion_palette(segments)
    assert result["emo_anger"].value == 0.0


def test_unknown_speaker_not_excluded():
    result = compute_emotion_palette([{"speaker": "UNKNOWN", "text": "он вообще псих"}])
    assert result["emo_anger"].support_n == 1


def test_empty_segments_returns_empty_dict():
    assert compute_emotion_palette([]) == {}


def test_empty_text_returns_empty_dict():
    assert compute_emotion_palette(_seg("")) == {}


def test_all_four_axes_present_when_any_contact_speech():
    result = compute_emotion_palette(_seg("просто обычный разговор ни о чём особенном"))
    assert set(result.keys()) == {"emo_anger", "emo_anxiety", "emo_joy", "emo_contempt"}
    assert all(f.value == 0.0 for f in result.values())
