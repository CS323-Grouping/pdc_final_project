from __future__ import annotations

from pathlib import Path

import pygame

from network import protocol
from world.constants import PLAYER_FRAME_HEIGHT, PLAYER_FRAME_SIZE, PLAYER_FRAME_WIDTH


def animation_path(project_root: Path, model_type: str, model_color: str) -> Path:
    model_type = protocol.normalize_model_type(model_type)
    model_color = protocol.normalize_model_color(model_color)
    root = project_root / "assets" / "player" / "animation"
    candidates = (
        root / f"PlayerModel{model_type}Animations_{model_color}.png",
        root / f"PlayerModel{model_type}Animations_{protocol.DEFAULT_MODEL_COLOR}.png",
        root / f"PlayerModel{protocol.DEFAULT_MODEL_TYPE}Animations_{protocol.DEFAULT_MODEL_COLOR}.png",
        root / "playerAnimationNormal_Blue.png",
    )
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def body_variation_sheet_path(project_root: Path, model_type: str) -> Path:
    model_type = protocol.normalize_model_type(model_type)
    return project_root / "assets" / "player" / "model" / f"PlayerModel{model_type}Body_Variation.png"


def default_head_texture_path(project_root: Path) -> Path:
    return project_root / "assets" / "player" / "texture" / "PlayerModelDefaultHead_Texture.png"


def load_default_head_texture(project_root: Path) -> pygame.Surface:
    path = default_head_texture_path(project_root)
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except (FileNotFoundError, pygame.error):
        avatar = pygame.Surface((14, 14), pygame.SRCALPHA)
        avatar.fill((74, 128, 212, 255))
        pygame.draw.rect(avatar, (236, 240, 255, 255), pygame.Rect(3, 2, 8, 5))
        pygame.draw.rect(avatar, (34, 52, 96, 255), pygame.Rect(2, 8, 10, 4))
        return avatar


def load_body_variation_frame(project_root: Path, model_type: str, model_color: str) -> pygame.Surface | None:
    path = body_variation_sheet_path(project_root, model_type)
    if not path.exists():
        return None
    try:
        sheet = pygame.image.load(str(path)).convert_alpha()
    except pygame.error:
        return None
    color = protocol.normalize_model_color(model_color)
    try:
        column = protocol.MODEL_COLORS.index(color)
    except ValueError:
        column = protocol.MODEL_COLORS.index(protocol.DEFAULT_MODEL_COLOR)
    frame = pygame.Surface(PLAYER_FRAME_SIZE, pygame.SRCALPHA)
    source_rect = pygame.Rect(column * PLAYER_FRAME_WIDTH, 0, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)
    frame.blit(sheet, (0, 0), source_rect)
    return frame
