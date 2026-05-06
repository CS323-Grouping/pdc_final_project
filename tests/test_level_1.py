from world.constants import PLAYABLE_RIGHT, PLAYABLE_X, PLATFORM_NORMAL_WIDTH
from world.level_1 import (
    LEVEL_1_CHUNKS,
    LEVEL_1_MAX_PLATFORM_GAP,
    LEVEL_1_MIN_PLATFORM_GAP,
    LEVEL_1_PLATFORMS,
    LEVEL_1_TARGET_HEIGHT,
)


def test_level_1_platform_specs_stay_inside_playable_width():
    for spec in LEVEL_1_PLATFORMS:
        assert PLAYABLE_X <= spec.x
        assert spec.x + PLATFORM_NORMAL_WIDTH <= PLAYABLE_RIGHT


def test_level_1_uses_vertical_tower_progression():
    y_values = [spec.y for spec in LEVEL_1_PLATFORMS]

    assert min(y_values) < 0
    assert max(y_values) <= 152


def test_level_1_platform_gaps_stay_jumpable_and_not_too_dense():
    y_values = [spec.y for spec in LEVEL_1_PLATFORMS]
    gaps = [current - nxt for current, nxt in zip(y_values, y_values[1:])]

    assert min(gaps) >= LEVEL_1_MIN_PLATFORM_GAP
    assert max(gaps) <= LEVEL_1_MAX_PLATFORM_GAP


def test_level_1_spans_about_twenty_chunks():
    y_values = [spec.y for spec in LEVEL_1_PLATFORMS]
    height = max(y_values) - min(y_values)

    assert LEVEL_1_CHUNKS == 20
    assert height >= LEVEL_1_TARGET_HEIGHT - 20
