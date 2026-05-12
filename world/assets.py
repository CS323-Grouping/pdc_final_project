from dataclasses import dataclass
from pathlib import Path

import pygame


@dataclass(frozen=True)
class WorldAssets:
    background: pygame.Surface
    border_left: pygame.Surface
    border_right: pygame.Surface
    ingame_borders: pygame.Surface
    ingame_panel: pygame.Surface
    platform_normal: pygame.Surface
    orb_frames: tuple[pygame.Surface, ...]


def _load_orb_frames(path: Path) -> tuple[pygame.Surface, ...]:
    sheet = pygame.image.load(str(path)).convert_alpha()
    frame_w = 16
    frame_h = sheet.get_height()
    frames = []
    for x in range(0, sheet.get_width(), frame_w):
        frames.append(sheet.subsurface(pygame.Rect(x, 0, frame_w, frame_h)).copy())
    return tuple(frames)


def load_world_assets(project_root: Path) -> WorldAssets:
    assets_root = project_root / "assets"
    ingame_root = assets_root / "inGame"
    return WorldAssets(
        background=pygame.image.load(
            str(ingame_root / "00_InGameBackground_Texture.png")
        ).convert_alpha(),
        border_left=pygame.image.load(
            str(assets_root / "worldBorder" / "borderNormalLeft_Level1.png")
        ).convert_alpha(),
        border_right=pygame.image.load(
            str(assets_root / "worldBorder" / "borderNormalRight_Level1.png")
        ).convert_alpha(),
        ingame_borders=pygame.image.load(
            str(ingame_root / "01_InGameBorders_Frame.png")
        ).convert_alpha(),
        ingame_panel=pygame.image.load(
            str(ingame_root / "02_InGamePanel_Frame.png")
        ).convert_alpha(),
        platform_normal=pygame.image.load(
            str(assets_root / "platforms" / "platformNormal_Level_1.png")
        ).convert_alpha(),
        orb_frames=_load_orb_frames(ingame_root / "Orb" / "RandomOrb_ModelGold-Sheet.png"),
    )
