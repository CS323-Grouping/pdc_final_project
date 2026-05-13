import math

from ui import animations as anim


def test_clamp01():
    assert anim.clamp01(-1) == 0.0
    assert anim.clamp01(0.3) == 0.3
    assert anim.clamp01(2) == 1.0


def test_fade_in_progress():
    assert anim.fade_in_progress(0, 0.2) == 0.0
    assert math.isclose(anim.fade_in_progress(0.1, 0.2), 0.5)
    assert anim.fade_in_progress(0.2, 0.2) == 1.0
    assert anim.fade_in_progress(9, 0) == 1.0


def test_pulse01_bounded():
    for t in (0, 0.25, 0.5, 0.9, 2.1):
        p = anim.pulse01(t, 0.8)
        assert 0.0 <= p <= 1.0


def test_stagger_alpha():
    assert anim.stagger_alpha(0, 2) == 0.0
    assert anim.stagger_alpha(0.5, 0, delay_per_row=0.1) == 1.0


def test_highlight_decay():
    assert anim.highlight_decay(1.0, 0.1, rate=2.8) < 1.0
    assert anim.highlight_decay(0.01, 1.0, rate=2.8) == 0.0
