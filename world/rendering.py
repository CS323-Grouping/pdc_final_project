import math

import pygame

from world.assets import WorldAssets
from world.constants import BORDER_WIDTH, CHUNK_HEIGHT, INTERNAL_HEIGHT, PLAYABLE_RIGHT


class LevelRenderer:
    def __init__(self, assets: WorldAssets):
        self.assets = assets

    def draw_background(self, surface: pygame.Surface, camera) -> None:
        first_chunk = math.floor(camera.y / CHUNK_HEIGHT)
        last_chunk = math.floor((camera.y + INTERNAL_HEIGHT) / CHUNK_HEIGHT)
        for chunk in range(first_chunk, last_chunk + 1):
            chunk_world_y = chunk * CHUNK_HEIGHT
            screen_y = int(round(chunk_world_y - camera.y))
            surface.blit(self.assets.background, (BORDER_WIDTH, screen_y))

    def draw_borders(self, surface: pygame.Surface) -> None:
        surface.blit(self.assets.border_left, (0, 0))
        surface.blit(self.assets.border_right, (PLAYABLE_RIGHT, 0))
