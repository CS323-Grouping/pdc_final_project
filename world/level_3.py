import random
from dataclasses import dataclass

from world.shapes import platform as plat
from world.constants import CHUNK_HEIGHT, INTERNAL_WIDTH, PLATFORM_NORMAL_SIZE


@dataclass(frozen=True)
class PlatformSpec:
    x: int
    y: int
    kind: str = "normal"


LEVEL_3_CHUNKS = 28
LEVEL_3_TARGET_HEIGHT = LEVEL_3_CHUNKS * CHUNK_HEIGHT
LEVEL_3_MIN_PLATFORM_GAP = 50
LEVEL_3_MAX_PLATFORM_GAP = 62


def _build_level_3_platforms() -> tuple[PlatformSpec, ...]:
    start_y = 152
    y = start_y
    platforms = [
    PlatformSpec(40, 152, "normal"),
    PlatformSpec(100, 152, "normal"),
    PlatformSpec(160, 152, "normal"),
    PlatformSpec(220, 152, "normal"),
]

    while True:
        if platforms:
            previous_x = platforms[-1].x
            min_x = max(40, previous_x - 110)
            max_x = min(INTERNAL_WIDTH - 80, previous_x + 110)
            x = random.randint(min_x, max_x)
        else:
            x = 100
        platforms.append(PlatformSpec(x, y))

        if (start_y - y) >= LEVEL_3_TARGET_HEIGHT:
            break

        y -= random.randint(
            LEVEL_3_MIN_PLATFORM_GAP,
            LEVEL_3_MAX_PLATFORM_GAP
        )

    return tuple(platforms)


LEVEL_3_PLATFORMS = _build_level_3_platforms()

LEVEL_3_TOP_Y: int = min(spec.y for spec in LEVEL_3_PLATFORMS) - 80

LEVEL_3_GOAL_Y: int = LEVEL_3_TOP_Y

LEVEL_3_GOAL_CENTER_X: int = INTERNAL_WIDTH // 2


def create_level_3(platform_image):
    random.seed(303)
    return [
        plat.Platform(
            (spec.x, spec.y),
            platform_image,
            collision_size=PLATFORM_NORMAL_SIZE,
        )
        for spec in LEVEL_3_PLATFORMS
    ]