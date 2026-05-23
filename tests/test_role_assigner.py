"""Tests for callprofiler.diarize.role_assigner — overlap-mapping speaker assignment."""
from callprofiler.diarize.role_assigner import assign_speakers
from callprofiler.models import Segment


def _seg(start_ms, end_ms, text="x", speaker="UNKNOWN"):
    return Segment(start_ms=start_ms, end_ms=end_ms, text=text, speaker=speaker)


def _dia(start_ms, end_ms, speaker):
    return {"start_ms": start_ms, "end_ms": end_ms, "speaker": speaker}


class TestEmptyInputs:
    def test_empty_segments_returns_empty(self):
        assert assign_speakers([], [{"start_ms": 0, "end_ms": 1000, "speaker": "OWNER"}]) == []

    def test_empty_diarization_returns_copy_with_unknown(self):
        segs = [_seg(0, 1000, "hello")]
        result = assign_speakers(segs, [])
        assert result[0].speaker == "UNKNOWN"
        assert result[0].text == "hello"

    def test_both_empty(self):
        assert assign_speakers([], []) == []


class TestOverlapAssignment:
    def test_single_segment_full_overlap(self):
        segs = [_seg(0, 500, "hi")]
        dias = [_dia(0, 500, "OWNER")]
        result = assign_speakers(segs, dias)
        assert result[0].speaker == "OWNER"

    def test_single_segment_partial_overlap(self):
        segs = [_seg(200, 800, "hi")]
        dias = [_dia(0, 500, "OWNER")]
        result = assign_speakers(segs, dias)
        assert result[0].speaker == "OWNER"

    def test_max_overlap_wins(self):
        segs = [_seg(0, 600, "hi")]
        dias = [
            _dia(0, 200, "OWNER"),      # overlap 200
            _dia(200, 700, "OTHER"),     # overlap 400 — wins
        ]
        result = assign_speakers(segs, dias)
        assert result[0].speaker == "OTHER"

    def test_multiple_segments(self):
        segs = [_seg(0, 400, "a"), _seg(500, 900, "b")]
        dias = [
            _dia(0, 600, "OWNER"),
            _dia(700, 1000, "OTHER"),
        ]
        result = assign_speakers(segs, dias)
        assert result[0].speaker == "OWNER"
        assert result[1].speaker == "OTHER"

    def test_zero_overlap_zero_segment(self):
        segs = [_seg(0, 0, "empty")]
        dias = [_dia(100, 200, "OWNER")]
        result = assign_speakers(segs, dias)
        assert result[0].speaker == "OWNER"


class TestNoOverlapFallback:
    def test_fallback_to_closest_by_start(self):
        segs = [_seg(0, 100, "hi")]
        dias = [_dia(500, 600, "OWNER")]
        result = assign_speakers(segs, dias)
        assert result[0].speaker == "OWNER"

    def test_fallback_picks_nearest(self):
        segs = [_seg(500, 600, "hi")]
        dias = [
            _dia(0, 100, "OWNER"),       # dist = 400
            _dia(800, 900, "OTHER"),      # dist = 200 — wins
        ]
        result = assign_speakers(segs, dias)
        assert result[0].speaker == "OTHER"


class TestImmutability:
    def test_original_segments_unchanged(self):
        segs = [_seg(0, 500, "hello", "UNKNOWN")]
        assign_speakers(segs, [_dia(0, 500, "OWNER")])
        assert segs[0].speaker == "UNKNOWN"

    def test_result_is_new_list(self):
        segs = [_seg(0, 500, "hello")]
        result = assign_speakers(segs, [_dia(0, 500, "OWNER")])
        assert result is not segs
        assert result[0] is not segs[0]
