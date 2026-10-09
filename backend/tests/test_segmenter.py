from app.models import ProcessingSettings
from app.pipeline.segmenter import pack_clips


def settings(**kw):
    return ProcessingSettings(**kw)


def test_close_phrases_merge_and_far_ones_split():
    spans = [(1.0, 3.0), (3.5, 5.0), (12.0, 15.0)]
    clips = pack_clips(spans, settings(), total_s=20.0)
    assert len(clips) == 2
    assert clips[0][0] < 1.0 and clips[0][1] > 5.0  # first two merged, padded
    assert clips[1][0] > 5.0  # padding never reaches into the previous clip


def test_clip_never_exceeds_max():
    spans = [(i * 4.0, i * 4.0 + 3.8) for i in range(10)]  # a pause of only 0.2 s between phrases
    s = settings(max_clip_s=10.0)
    for lo, hi in pack_clips(spans, s, total_s=60.0):
        assert hi - lo <= 10.0 + 2 * s.pad_ms / 1000 + 1e-6


def test_too_short_speech_is_dropped():
    assert pack_clips([(1.0, 1.8)], settings(), total_s=10.0) == []


def test_padding_is_clamped_to_file_bounds():
    (lo, hi), = pack_clips([(0.05, 4.0)], settings(), total_s=4.1)
    assert lo == 0.0 and hi <= 4.1


def test_neighbours_share_the_gap_midpoint():
    clips = pack_clips([(1.0, 4.0), (6.0, 9.0)], settings(merge_gap_s=0.5, pad_ms=600), total_s=12.0)
    assert clips[0][1] <= 5.0 <= clips[1][0] + 1e-6  # midpoint of the 4.0..6.0 gap


def test_equal_min_max_cuts_strict_fixed_length_windows():
    # Speech scattered across ~140 s; fixed 46 s mode should ignore pause boundaries entirely.
    spans = [(2.0, 5.0), (50.0, 53.0), (96.0, 99.0), (130.0, 133.0)]
    s = settings(min_clip_s=46.0, max_clip_s=46.0)
    clips = pack_clips(spans, s, total_s=140.0)
    assert all(round(hi - lo, 3) == 46.0 for lo, hi in clips)
    assert clips == [(0.0, 46.0), (46.0, 92.0), (92.0, 138.0)]


def test_fixed_length_drops_silent_windows_and_short_remainder():
    # No speech at all in the second 46 s window; total_s leaves only a 10 s remainder after two windows.
    s = settings(min_clip_s=46.0, max_clip_s=46.0)
    clips = pack_clips([(2.0, 5.0), (100.0, 103.0)], s, total_s=102.0)
    assert clips == [(0.0, 46.0)]  # window 2 (46-92) has no speech; the 92-102 remainder is < 46 s
