from dataclasses import dataclass
from pathlib import Path

import pygame


@dataclass(frozen=True)
class WorldAssets:
    background: pygame.Surface
    border_left: pygame.Surface
    border_right: pygame.Surface
    platform_normal: pygame.Surface


def load_world_assets(project_root: Path) -> WorldAssets:
    assets_root = project_root / "assets"
    return WorldAssets(
        background=pygame.image.load(
            str(assets_root / "worldBackground" / "backgroundNormal_Level1.png")
        ).convert_alpha(),
        border_left=pygame.image.load(
            str(assets_root / "worldBorder" / "borderNormalLeft_Level1.png")
        ).convert_alpha(),
        border_right=pygame.image.load(
            str(assets_root / "worldBorder" / "borderNormalRight_Level1.png")
        ).convert_alpha(),
        platform_normal=pygame.image.load(
            str(assets_root / "platforms" / "platformNormal_Level_1.png")
        ).convert_alpha(),
    )
