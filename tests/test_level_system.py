from network import protocol
from world import level_system
from world.constants import (
    PLATFORM_WIDTH_OPTIONS,
    PLAYABLE_RIGHT,
    PLAYABLE_WIDTH,
    PLAYABLE_X,
    PLAYER_MAX_NORMAL_JUMP_PLATFORM_GAP,
    PLAYER_MIN_PLATFORM_VERTICAL_GAP,
    PLAYER_NORMAL_JUMP_HEIGHT,
)


def test_level_configs_match_wire_level_ids():
    assert level_system.DEFAULT_LEVEL_ID == protocol.DEFAULT_LEVEL_ID
    assert level_system.AVAILABLE_LEVEL_IDS == protocol.LEVEL_IDS
    assert tuple(sorted(level_system.LEVEL_CONFIGS)) == protocol.LEVEL_IDS
    assert protocol.LEVEL_IDS == tuple(range(1, 11))
    assert level_system.LEVEL_CONFIGS[1].chunks == 10
    assert tuple(config.chunks for config in level_system.LEVEL_CONFIGS.values()) == tuple(range(10, 30, 2))


def test_generate_level_is_deterministic_for_level_and_seed():
    first = level_system.generate_level(2, 123456)
    second = level_system.generate_level(2, 123456)

    assert first == second
    assert first.level_id == 2
    assert first.seed == 123456


def test_generate_level_keeps_platforms_inside_playable_bounds():
    for level_id in protocol.LEVEL_IDS:
        generated = level_system.generate_level(level_id, 1000 + level_id)
        config = generated.config

        assert len(generated.platforms) >= config.platform_count
        assert generated.goal_y == min(spec.y for spec in generated.platforms) - config.goal_headroom
        for current in generated.platforms:
            assert config.min_x <= current.x
            assert current.x + current.width <= PLAYABLE_RIGHT

        row_y_values = sorted({spec.y for spec in generated.platforms}, reverse=True)
        for previous_y, current_y in zip(row_y_values, row_y_values[1:]):
            vertical_gap = previous_y - current_y
            assert config.min_vertical_gap <= vertical_gap <= config.max_vertical_gap


def test_level_vertical_gaps_stay_below_normal_jump_height():
    assert PLAYER_MAX_NORMAL_JUMP_PLATFORM_GAP < PLAYER_NORMAL_JUMP_HEIGHT
    for config in level_system.LEVEL_CONFIGS.values():
        assert config.min_vertical_gap >= PLAYER_MIN_PLATFORM_VERTICAL_GAP
        assert config.max_vertical_gap <= PLAYER_MAX_NORMAL_JUMP_PLATFORM_GAP


def test_levels_use_full_width_start_and_goal():
    for level_id in protocol.LEVEL_IDS:
        generated = level_system.generate_level(level_id, 1000 + level_id)
        start = generated.platforms[0]

        assert start.x == PLAYABLE_X
        assert start.width == PLAYABLE_WIDTH
        assert generated.goal_center_x == PLAYABLE_X + PLAYABLE_WIDTH // 2
        assert generated.goal_width == PLAYABLE_WIDTH


def test_generated_levels_include_variable_widths_and_branch_rows():
    for level_id in protocol.LEVEL_IDS:
        generated = level_system.generate_level(level_id, 2000 + level_id)
        widths = {spec.width for spec in generated.platforms[1:]}
        row_counts = {}
        for spec in generated.platforms:
            row_counts[spec.row] = row_counts.get(spec.row, 0) + 1

        assert widths <= set(PLATFORM_WIDTH_OPTIONS)
        assert len(widths) >= 2
        assert any(row != 0 and count >= 2 for row, count in row_counts.items())


def test_generated_primary_path_remains_reachable():
    for level_id in protocol.LEVEL_IDS:
        generated = level_system.generate_level(level_id, 3000 + level_id)
        primary_by_row = {}
        for spec in generated.platforms:
            primary_by_row.setdefault(spec.row, spec)

        previous = primary_by_row[0]
        for row in range(1, max(primary_by_row) + 1):
            current = primary_by_row[row]
            assert level_system._is_reachable_transition(previous, current, generated.config)
            previous = current


def test_generated_rows_do_not_create_overhead_traps():
    for level_id in protocol.LEVEL_IDS:
        generated = level_system.generate_level(level_id, 4000 + level_id)
        rows = {}
        for spec in generated.platforms:
            rows.setdefault(spec.row, []).append(spec)

        for row in range(1, max(rows) + 1):
            for lower in rows[row - 1]:
                assert any(level_system._is_reachable_transition(lower, upper, generated.config) for upper in rows[row])
                for upper in rows[row]:
                    assert level_system._is_safe_overhead(lower, upper)
