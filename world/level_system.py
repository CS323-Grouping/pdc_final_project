from __future__ import annotations

from dataclasses import dataclass
import random

from network import protocol
from world.constants import (
    CHUNK_HEIGHT,
    PLAYER_GRAVITY,
    PLAYER_HITBOX_WIDTH,
    PLAYER_JUMP_VELOCITY,
    PLAYER_MAX_NORMAL_JUMP_PLATFORM_GAP,
    PLAYER_MIN_PLATFORM_VERTICAL_GAP,
    PLAYER_MOVE_SPEED,
    PLAYER_PLATFORM_SIDE_CLEARANCE,
    PLAYER_SAME_ROW_GAP_BASE,
    PLAYER_SAME_ROW_GAP_MAX,
    PLAYER_SAME_ROW_GAP_PER_LEVEL,
    PLAYER_VERTICAL_MIN_GAP_EXTRA_MAX,
    PLAYER_VERTICAL_MIN_GAP_EXTRA_PER_LEVEL_STEP,
    PLATFORM_NORMAL_HEIGHT,
    PLATFORM_NORMAL_WIDTH,
    PLAYABLE_RIGHT,
    PLAYABLE_WIDTH,
    PLAYABLE_X,
)

DEFAULT_LEVEL_ID = protocol.DEFAULT_LEVEL_ID
AVAILABLE_LEVEL_IDS = protocol.LEVEL_IDS
JUMP_REACHABILITY_DT = 1.0 / 60.0
JUMP_REACHABILITY_MAX_SECONDS = 1.25
HORIZONTAL_JUMP_SAFETY_MARGIN = 6.0


@dataclass(frozen=True)
class PlatformSpec:
    x: int
    y: int
    kind: str = "normal"
    width: int = PLATFORM_NORMAL_WIDTH
    row: int = 0


@dataclass(frozen=True)
class PlatformTypeWeight:
    kind: str
    weight: int


@dataclass(frozen=True)
class PlatformWidthWeight:
    width: int
    weight: int


@dataclass(frozen=True)
class BuffDebuffRule:
    kind: str
    weight: int


@dataclass(frozen=True)
class BuffDebuffConfig:
    enabled: bool
    min_platform_interval: int
    max_platform_interval: int
    rules: tuple[BuffDebuffRule, ...] = ()


@dataclass(frozen=True)
class LevelConfig:
    level_id: int
    chunks: int
    platform_count: int
    start_y: int
    min_vertical_gap: int
    max_vertical_gap: int
    min_horizontal_gap: int
    max_horizontal_gap: int
    min_x: int
    max_x: int
    platform_widths: tuple[PlatformWidthWeight, ...]
    platform_types: tuple[PlatformTypeWeight, ...]
    buff_debuff: BuffDebuffConfig
    branch_chance: float = 0.0
    branch_every: int = 0
    goal_headroom: int = 80
    start_platform: PlatformSpec = PlatformSpec(PLAYABLE_X, 152, "normal", PLAYABLE_WIDTH, 0)


@dataclass(frozen=True)
class GeneratedLevel:
    level_id: int
    seed: int
    platforms: tuple[PlatformSpec, ...]
    goal_center_x: int
    goal_y: int
    goal_width: int
    config: LevelConfig


LEVEL_CHUNK_START = 10
LEVEL_CHUNK_STEP = 2
LEVEL_PLATFORM_DENSITY = 5

LEVEL_PLATFORM_WIDTH_PROFILES: dict[int, tuple[PlatformWidthWeight, ...]] = {
    1: (
        PlatformWidthWeight(48, 15),
        PlatformWidthWeight(65, 80),
        PlatformWidthWeight(96, 5),
    ),
    2: (
        PlatformWidthWeight(48, 20),
        PlatformWidthWeight(65, 75),
        PlatformWidthWeight(96, 5),
    ),
    3: (
        PlatformWidthWeight(40, 8),
        PlatformWidthWeight(48, 24),
        PlatformWidthWeight(65, 63),
        PlatformWidthWeight(96, 5),
    ),
    4: (
        PlatformWidthWeight(40, 14),
        PlatformWidthWeight(48, 30),
        PlatformWidthWeight(65, 52),
        PlatformWidthWeight(96, 4),
    ),
    5: (
        PlatformWidthWeight(32, 5),
        PlatformWidthWeight(40, 20),
        PlatformWidthWeight(48, 34),
        PlatformWidthWeight(65, 38),
        PlatformWidthWeight(96, 3),
    ),
    6: (
        PlatformWidthWeight(32, 10),
        PlatformWidthWeight(40, 24),
        PlatformWidthWeight(48, 36),
        PlatformWidthWeight(65, 28),
        PlatformWidthWeight(96, 2),
    ),
    7: (
        PlatformWidthWeight(32, 16),
        PlatformWidthWeight(40, 29),
        PlatformWidthWeight(48, 36),
        PlatformWidthWeight(65, 18),
        PlatformWidthWeight(96, 1),
    ),
    8: (
        PlatformWidthWeight(32, 22),
        PlatformWidthWeight(40, 34),
        PlatformWidthWeight(48, 32),
        PlatformWidthWeight(65, 12),
    ),
    9: (
        PlatformWidthWeight(32, 30),
        PlatformWidthWeight(40, 38),
        PlatformWidthWeight(48, 26),
        PlatformWidthWeight(65, 6),
    ),
    10: (
        PlatformWidthWeight(32, 38),
        PlatformWidthWeight(40, 40),
        PlatformWidthWeight(48, 18),
        PlatformWidthWeight(65, 4),
    ),
}


def _level_chunks(level_id: int) -> int:
    return LEVEL_CHUNK_START + (level_id - 1) * LEVEL_CHUNK_STEP


def _scaled_min_horizontal_gap(level_id: int) -> int:
    return min(
        PLAYER_SAME_ROW_GAP_MAX,
        PLAYER_SAME_ROW_GAP_BASE + (level_id - 1) * PLAYER_SAME_ROW_GAP_PER_LEVEL,
    )


def _scaled_max_config_horizontal_gap(level_id: int) -> int:
    """Upper bound for horizontal offset in config; each jump still clamped by reachability."""
    return min(72, 32 + (level_id - 1) * 4)


def _scaled_vertical_gap_bounds(level_id: int) -> tuple[int, int]:
    max_v = PLAYER_MAX_NORMAL_JUMP_PLATFORM_GAP
    extra = min(
        PLAYER_VERTICAL_MIN_GAP_EXTRA_MAX,
        max(0, (level_id - 1) // PLAYER_VERTICAL_MIN_GAP_EXTRA_PER_LEVEL_STEP),
    )
    min_v = min(PLAYER_MIN_PLATFORM_VERTICAL_GAP + extra, max_v)
    return min_v, max_v


def _make_level_config(level_id: int) -> LevelConfig:
    chunks = _level_chunks(level_id)
    branch_chance = min(0.42, 0.10 + level_id * 0.032)
    min_v, max_v = _scaled_vertical_gap_bounds(level_id)
    return LevelConfig(
        level_id=level_id,
        chunks=chunks,
        platform_count=chunks * LEVEL_PLATFORM_DENSITY,
        start_y=152,
        min_vertical_gap=min_v,
        max_vertical_gap=max_v,
        min_horizontal_gap=_scaled_min_horizontal_gap(level_id),
        max_horizontal_gap=_scaled_max_config_horizontal_gap(level_id),
        min_x=PLAYABLE_X,
        max_x=PLAYABLE_RIGHT,
        platform_widths=LEVEL_PLATFORM_WIDTH_PROFILES[level_id],
        platform_types=(PlatformTypeWeight("normal", 100),),
        buff_debuff=BuffDebuffConfig(
            enabled=False,
            min_platform_interval=max(6, 12 - level_id // 2),
            max_platform_interval=max(10, 18 - level_id // 2),
        ),
        branch_chance=branch_chance,
        branch_every=max(5, 15 - level_id),
    )


LEVEL_CONFIGS: dict[int, LevelConfig] = {
    level_id: _make_level_config(level_id)
    for level_id in AVAILABLE_LEVEL_IDS
}


def normalize_level_id(level_id: int) -> int:
    normalized = protocol.normalize_level_id(level_id)
    if normalized in LEVEL_CONFIGS:
        return normalized
    return DEFAULT_LEVEL_ID


def level_label(level_id: int) -> str:
    return f"Level {normalize_level_id(level_id)}"


def level_preview_seed(level_id: int) -> int:
    return 100 + normalize_level_id(level_id)


def _weighted_kind(rng: random.Random, types: tuple[PlatformTypeWeight, ...]) -> str:
    total_weight = sum(max(0, item.weight) for item in types)
    if total_weight <= 0:
        return "normal"
    roll = rng.randint(1, total_weight)
    running = 0
    for item in types:
        running += max(0, item.weight)
        if roll <= running:
            return item.kind
    return types[-1].kind


def _max_left_for_width(config: LevelConfig, width: int) -> int:
    return max(config.min_x, min(config.max_x, PLAYABLE_RIGHT) - width)


def _clamp_x_for_width(config: LevelConfig, x: int, width: int) -> int:
    return max(config.min_x, min(_max_left_for_width(config, width), int(x)))


def _horizontal_edge_gap(left: PlatformSpec, right: PlatformSpec) -> int:
    if left.x + left.width < right.x:
        return right.x - (left.x + left.width)
    if right.x + right.width < left.x:
        return left.x - (right.x + right.width)
    return 0


def _overlap_width(left: PlatformSpec, right: PlatformSpec) -> int:
    return max(0, min(left.x + left.width, right.x + right.width) - max(left.x, right.x))


def _max_horizontal_edge_gap_for_vertical_gap(vertical_gap: int, config: LevelConfig) -> int:
    target_y = -max(0, vertical_gap)
    y = 0.0
    velocity = PLAYER_JUMP_VELOCITY
    elapsed = 0.0
    reached_height = target_y >= 0

    while elapsed < JUMP_REACHABILITY_MAX_SECONDS:
        velocity += PLAYER_GRAVITY * JUMP_REACHABILITY_DT
        y += velocity * JUMP_REACHABILITY_DT
        elapsed += JUMP_REACHABILITY_DT
        if y <= target_y:
            reached_height = True
        if reached_height and velocity >= 0 and y >= target_y:
            break
    else:
        return -1

    max_center_travel = PLAYER_MOVE_SPEED * elapsed
    usable_edge_gap = max_center_travel - PLAYER_HITBOX_WIDTH - HORIZONTAL_JUMP_SAFETY_MARGIN
    return max(0, min(config.max_horizontal_gap, int(usable_edge_gap)))


def _has_side_entry_clearance(lower: PlatformSpec, upper: PlatformSpec) -> bool:
    left_clearance = upper.x - lower.x
    right_clearance = (lower.x + lower.width) - (upper.x + upper.width)
    return max(left_clearance, right_clearance) >= PLAYER_PLATFORM_SIDE_CLEARANCE


def _is_allowed_overhead(lower: PlatformSpec, upper: PlatformSpec) -> bool:
    if lower.width >= PLAYABLE_WIDTH:
        return _has_side_entry_clearance(lower, upper)
    if upper.width > lower.width:
        return False
    return _has_side_entry_clearance(lower, upper)


def _is_reachable_transition(lower: PlatformSpec, upper: PlatformSpec, config: LevelConfig) -> bool:
    vertical_gap = lower.y - upper.y
    if vertical_gap < config.min_vertical_gap or vertical_gap > config.max_vertical_gap:
        return False
    edge_gap = _horizontal_edge_gap(lower, upper)
    if edge_gap > 0:
        return edge_gap <= _max_horizontal_edge_gap_for_vertical_gap(vertical_gap, config)
    if _overlap_width(lower, upper) <= 0:
        return _max_horizontal_edge_gap_for_vertical_gap(vertical_gap, config) >= 0
    return _is_allowed_overhead(lower, upper)


def _is_safe_overhead(lower: PlatformSpec, upper: PlatformSpec) -> bool:
    if _overlap_width(lower, upper) <= 0:
        return True
    return _is_allowed_overhead(lower, upper)


def _is_separated_from_row(candidate: PlatformSpec, row_platforms: list[PlatformSpec], config: LevelConfig) -> bool:
    return all(
        _overlap_width(candidate, existing) == 0
        and _horizontal_edge_gap(candidate, existing) >= config.min_horizontal_gap
        for existing in row_platforms
    )


def _platform_width(rng: random.Random, config: LevelConfig) -> int:
    weights = tuple(item for item in config.platform_widths if item.width > 0 and item.weight > 0)
    if not weights:
        return PLATFORM_NORMAL_WIDTH
    total_weight = sum(item.weight for item in weights)
    roll = rng.randint(1, total_weight)
    running = 0
    for item in weights:
        running += item.weight
        if roll <= running:
            return int(item.width)
    return int(weights[-1].width)


def _reachable_x_range(previous: PlatformSpec, width: int, y: int, config: LevelConfig) -> tuple[int, int]:
    vertical_gap = previous.y - y
    max_horizontal_gap = _max_horizontal_edge_gap_for_vertical_gap(vertical_gap, config)
    if max_horizontal_gap < 0:
        return (1, 0)
    min_x = previous.x - width - max_horizontal_gap
    max_x = previous.x + previous.width + max_horizontal_gap
    return (
        max(config.min_x, int(min_x)),
        min(_max_left_for_width(config, width), int(max_x)),
    )


def _pick_next_x(rng: random.Random, previous: PlatformSpec, width: int, y: int, config: LevelConfig) -> int:
    min_x, max_x = _reachable_x_range(previous, width, y, config)
    if min_x > max_x:
        center_x = previous.x + (previous.width - width) // 2
        return _clamp_x_for_width(config, center_x, width)
    for _ in range(48):
        x = rng.randint(min_x, max_x)
        candidate = PlatformSpec(x, y, previous.kind, width, previous.row + 1)
        if _is_reachable_transition(previous, candidate, config):
            return x
    side = -1 if rng.random() < 0.5 else 1
    if side < 0:
        x = previous.x - width - config.min_horizontal_gap
    else:
        x = previous.x + previous.width + config.min_horizontal_gap
    return _clamp_x_for_width(config, x, width)


def _should_add_branch(rng: random.Random, row: int, config: LevelConfig) -> bool:
    if config.branch_every > 0 and row % config.branch_every == 0:
        return True
    return rng.random() < config.branch_chance


def _build_candidate(
    rng: random.Random,
    anchor: PlatformSpec,
    previous_row: list[PlatformSpec],
    row_platforms: list[PlatformSpec],
    y: int,
    row: int,
    config: LevelConfig,
) -> PlatformSpec | None:
    for _ in range(64):
        width = _platform_width(rng, config)
        x = _pick_next_x(rng, anchor, width, y, config)
        kind = _weighted_kind(rng, config.platform_types)
        candidate = PlatformSpec(x, y, kind, width, row)
        if not _is_reachable_transition(anchor, candidate, config):
            continue
        if not all(_is_safe_overhead(previous, candidate) for previous in previous_row):
            continue
        if not _is_separated_from_row(candidate, row_platforms, config):
            continue
        return candidate
    return _scan_candidate(anchor, previous_row, row_platforms, y, row, config)


def _scan_candidate(
    anchor: PlatformSpec,
    previous_row: list[PlatformSpec],
    row_platforms: list[PlatformSpec],
    y: int,
    row: int,
    config: LevelConfig,
) -> PlatformSpec | None:
    widths = sorted((item.width for item in config.platform_widths if item.width > 0), key=lambda value: abs(value - PLATFORM_NORMAL_WIDTH))
    if not widths:
        widths = [PLATFORM_NORMAL_WIDTH]
    for width in widths:
        min_x, max_x = _reachable_x_range(anchor, width, y, config)
        for x in range(min_x, max_x + 1):
            candidate = PlatformSpec(x, y, "normal", width, row)
            if not _is_reachable_transition(anchor, candidate, config):
                continue
            if not all(_is_safe_overhead(previous, candidate) for previous in previous_row):
                continue
            if not _is_separated_from_row(candidate, row_platforms, config):
                continue
            return candidate
    return None


def _build_shared_candidate(
    rng: random.Random,
    anchors: list[PlatformSpec],
    y: int,
    row: int,
    config: LevelConfig,
) -> PlatformSpec | None:
    for _ in range(96):
        width = _platform_width(rng, config)
        x = rng.randint(config.min_x, _max_left_for_width(config, width))
        kind = _weighted_kind(rng, config.platform_types)
        candidate = PlatformSpec(x, y, kind, width, row)
        if all(_is_reachable_transition(anchor, candidate, config) for anchor in anchors):
            return candidate
    return _scan_shared_candidate(anchors, y, row, config)


def _scan_shared_candidate(
    anchors: list[PlatformSpec],
    y: int,
    row: int,
    config: LevelConfig,
) -> PlatformSpec | None:
    widths = sorted((item.width for item in config.platform_widths if item.width > 0), key=lambda value: abs(value - PLATFORM_NORMAL_WIDTH))
    if not widths:
        widths = [PLATFORM_NORMAL_WIDTH]
    for width in widths:
        for x in range(config.min_x, _max_left_for_width(config, width) + 1):
            candidate = PlatformSpec(x, y, "normal", width, row)
            if all(_is_reachable_transition(anchor, candidate, config) for anchor in anchors):
                return candidate
    return None


def _fallback_candidate(
    anchor: PlatformSpec,
    previous_row: list[PlatformSpec],
    row_platforms: list[PlatformSpec],
    y: int,
    row: int,
    config: LevelConfig,
) -> PlatformSpec | None:
    width = min((item.width for item in config.platform_widths), default=PLATFORM_NORMAL_WIDTH)
    offsets = (
        anchor.x + anchor.width + config.min_horizontal_gap,
        anchor.x - width - config.min_horizontal_gap,
        anchor.x + (anchor.width - width) // 2,
    )
    for x in offsets:
        candidate = PlatformSpec(_clamp_x_for_width(config, x, width), y, "normal", width, row)
        if not _is_reachable_transition(anchor, candidate, config):
            continue
        if not all(_is_safe_overhead(previous, candidate) for previous in previous_row):
            continue
        if not _is_separated_from_row(candidate, row_platforms, config):
            continue
        return candidate
    return _scan_candidate(anchor, previous_row, row_platforms, y, row, config)


def generate_level(level_id: int, seed: int) -> GeneratedLevel:
    level_id = normalize_level_id(level_id)
    config = LEVEL_CONFIGS[level_id]
    rng = random.Random(int(seed) & 0xFFFFFFFF)

    y = config.start_y
    target_height = config.chunks * CHUNK_HEIGHT
    platforms: list[PlatformSpec] = [config.start_platform]
    primary = config.start_platform
    previous_row = [config.start_platform]
    row = 0

    while len(platforms) < config.platform_count or (config.start_y - y) < target_height:
        row += 1
        y -= rng.randint(config.min_vertical_gap, config.max_vertical_gap)
        row_platforms: list[PlatformSpec] = []

        if len(previous_row) > 1:
            primary = _build_shared_candidate(rng, previous_row, y, row, config)
            if primary is not None:
                row_platforms.append(primary)

        if not row_platforms:
            anchor = primary if primary in previous_row else previous_row[0]
            primary = _build_candidate(rng, anchor, previous_row, row_platforms, y, row, config)
            if primary is None:
                primary = _fallback_candidate(anchor, previous_row, row_platforms, y, row, config)
            if primary is None:
                primary = _scan_candidate(previous_row[0], previous_row, row_platforms, y, row, config)
            if primary is None:
                raise RuntimeError(f"Unable to generate reachable level row level={level_id} seed={seed} row={row}")
            row_platforms.append(primary)

        for previous in previous_row:
            if any(_is_reachable_transition(previous, current, config) for current in row_platforms):
                continue
            reconnect = _build_candidate(rng, previous, previous_row, row_platforms, y, row, config)
            if reconnect is None:
                reconnect = _fallback_candidate(previous, previous_row, row_platforms, y, row, config)
            if reconnect is not None and _is_separated_from_row(reconnect, row_platforms, config):
                row_platforms.append(reconnect)
            else:
                shared = _build_shared_candidate(rng, previous_row, y, row, config)
                if shared is not None:
                    row_platforms = [shared]
                    primary = shared
                    break
                raise RuntimeError(f"Unable to reconnect level row level={level_id} seed={seed} row={row}")

        if _should_add_branch(rng, row, config) and len(row_platforms) < 2:
            anchor = rng.choice(previous_row)
            branch = _build_candidate(rng, anchor, previous_row, row_platforms, y, row, config)
            if branch is not None:
                row_platforms.append(branch)

        platforms.extend(row_platforms)
        previous_row = row_platforms

    goal_y = min(spec.y for spec in platforms) - config.goal_headroom
    return GeneratedLevel(
        level_id=level_id,
        seed=int(seed) & 0xFFFFFFFF,
        platforms=tuple(platforms),
        goal_center_x=PLAYABLE_X + PLAYABLE_WIDTH // 2,
        goal_y=goal_y,
        goal_width=PLAYABLE_WIDTH,
        config=config,
    )


def create_level_platforms(layout: GeneratedLevel, platform_image):
    import pygame
    from world.shapes import platform as plat

    platforms = []
    for spec in layout.platforms:
        image = platform_image
        if image.get_width() != spec.width:
            image = pygame.transform.scale(image, (spec.width, image.get_height()))
        platforms.append(
            plat.Platform(
                (spec.x, spec.y),
                image,
                collision_size=(spec.width, PLATFORM_NORMAL_HEIGHT),
            )
        )
    return platforms
