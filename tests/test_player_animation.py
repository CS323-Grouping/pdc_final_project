from player_scripts.animation import ANIMATIONS
from player_scripts.avatar_sprite import AVATAR_RECT, HEAD_OUTER_RECT
from world.constants import PLAYER_FRAME_HEIGHT, PLAYER_FRAME_WIDTH


def test_player_animation_metadata_matches_sheet_layout():
    assert PLAYER_FRAME_WIDTH == 24
    assert PLAYER_FRAME_HEIGHT == 32
    assert len(ANIMATIONS) == 6
    assert {metadata["row"] for metadata in ANIMATIONS.values()} == set(range(6))


def test_jump_states_use_full_non_looping_rows():
    assert ANIMATIONS["jump_front"]["frames"] == 8
    assert ANIMATIONS["jump_left"]["frames"] == 8
    assert ANIMATIONS["jump_right"]["frames"] == 8
    assert ANIMATIONS["jump_front"]["loop"] is False
    assert ANIMATIONS["jump_left"]["loop"] is False
    assert ANIMATIONS["jump_right"]["loop"] is False


def test_avatar_slot_uses_expected_inset_inside_head_frame():
    assert HEAD_OUTER_RECT.size == (16, 16)
    assert AVATAR_RECT.size == (14, 14)
    assert AVATAR_RECT.x == HEAD_OUTER_RECT.x + 1
    assert AVATAR_RECT.y == HEAD_OUTER_RECT.y + 1
