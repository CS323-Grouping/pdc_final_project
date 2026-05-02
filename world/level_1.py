from dataclasses import dataclass

from world.shapes import platform as plat
from world.constants import CHUNK_HEIGHT, PLATFORM_NORMAL_SIZE


@dataclass(frozen=True)
class PlatformSpec:
    x: int
    y: int
    kind: str = "normal"


LEVEL_1_CHUNKS = 10
LEVEL_1_TARGET_HEIGHT = LEVEL_1_CHUNKS * CHUNK_HEIGHT
LEVEL_1_MIN_PLATFORM_GAP = 38
LEVEL_1_MAX_PLATFORM_GAP = 44

LEVEL_1_X_SEQUENCE = (
    96,
    176,
    66,
    190,
    110,
    48,
    170,
    82,
    196,
    120,
    58,
    180,
    92,
    206,
    130,
    70,
    188,
    102,
    50,
    160,
    84,
    202,
    118,
    64,
    174,
    96,
    210,
    136,
    76,
    190,
    108,
    54,
    166,
    88,
    198,
    124,
    68,
    182,
    100,
    214,
    142,
    80,
    194,
    112,
    60,
)

LEVEL_1_PLATFORM_GAPS = (
    40,
    40,
    42,
    38,
    44,
    40,
    42,
    38,
    40,
    44,
    38,
    42,
    40,
    40,
    44,
    38,
    42,
    40,
    38,
    44,
    40,
    42,
    38,
    40,
    44,
    38,
    42,
    40,
    40,
    44,
    38,
    42,
    40,
    38,
    44,
    40,
    42,
    38,
    40,
    44,
    38,
    42,
    40,
    40,
)


def _build_level_1_platforms() -> tuple[PlatformSpec, ...]:
    y = 152
    platforms = []
    for index, x in enumerate(LEVEL_1_X_SEQUENCE):
        platforms.append(PlatformSpec(x, y))
        if index < len(LEVEL_1_PLATFORM_GAPS):
            y -= LEVEL_1_PLATFORM_GAPS[index]
    return tuple(platforms)


LEVEL_1_PLATFORMS = _build_level_1_platforms()


def create_level_1(platform_image):
    return [
        plat.Platform(
            (spec.x, spec.y),
            platform_image,
            collision_size=PLATFORM_NORMAL_SIZE,
        )
        for spec in LEVEL_1_PLATFORMS
    ]
