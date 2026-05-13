import math

import pygame

from world.assets import WorldAssets
from world.constants import CHUNK_HEIGHT, INTERNAL_HEIGHT, PLAYABLE_X


INGAME_BORDERS_POS = (70, 0)
INGAME_PANEL_POS = (0, 0)


def draw_static_game_frame(surface: pygame.Surface, assets: WorldAssets, camera_y: float = 0.0) -> None:
    """Tile the in-game level background and draw left/right border overlays (no entities).

    Use this for full-screen UI such as match results so the backdrop matches gameplay.
    `camera_y` selects which part of the tower is visible (same convention as gameplay camera).

    Unlike `LevelRenderer.draw_background`, this covers the full `surface` height (e.g. window-
    sized overlays) by iterating enough vertical chunks, and tiles the border art when needed.
    """

    sh = surface.get_height()
    first_chunk = math.floor(camera_y / CHUNK_HEIGHT)
    last_chunk = math.floor((camera_y + sh - 1) / CHUNK_HEIGHT)
    for chunk in range(first_chunk, last_chunk + 1):
        chunk_world_y = chunk * CHUNK_HEIGHT
        screen_y = int(round(chunk_world_y - camera_y))
        surface.blit(assets.background, (PLAYABLE_X, screen_y))

    y = 0
    while y < sh:
        surface.blit(assets.ingame_borders, (INGAME_BORDERS_POS[0], y))
        surface.blit(assets.ingame_panel, (INGAME_PANEL_POS[0], y))
        y += assets.ingame_panel.get_height()


class LevelRenderer:
    def __init__(self, assets: WorldAssets):
        self.assets = assets

    def draw_background(self, surface: pygame.Surface, camera) -> None:
        first_chunk = math.floor(camera.y / CHUNK_HEIGHT)
        last_chunk = math.floor((camera.y + INTERNAL_HEIGHT) / CHUNK_HEIGHT)
        for chunk in range(first_chunk, last_chunk + 1):
            chunk_world_y = chunk * CHUNK_HEIGHT
            screen_y = int(round(chunk_world_y - camera.y))
            surface.blit(self.assets.background, (PLAYABLE_X, screen_y))

    def draw_borders(self, surface: pygame.Surface) -> None:
        surface.blit(self.assets.ingame_borders, INGAME_BORDERS_POS)
        surface.blit(self.assets.ingame_panel, INGAME_PANEL_POS)
