import pygame


GOAL_WIDTH = 64
GOAL_HEIGHT = 16


class Goal:
    def __init__(self, center_x: int, world_y: int):
        self.rect = pygame.Rect(0, 0, GOAL_WIDTH, GOAL_HEIGHT)
        self.rect.centerx = center_x
        self.rect.top = world_y
        self._pulse = 0.0

    def update(self, dt: float) -> None:
        import math
        self._pulse = (self._pulse + dt * 2.0) % (2 * math.pi)

    def draw(self, surface: pygame.Surface, camera=None) -> None:
        import math
        rect = self.rect
        if camera is not None:
            rect = rect.move(-int(round(camera.x)), -int(round(camera.y)))

        brightness = int(180 + 60 * math.sin(self._pulse))
        core_color = (brightness, brightness, 60)
        glow_color = (brightness // 2, brightness // 2, 20)

        glow_rect = rect.inflate(4, 4)
        pygame.draw.rect(surface, glow_color, glow_rect, border_radius=4)
        pygame.draw.rect(surface, core_color, rect, border_radius=3)
        stripe = pygame.Rect(rect.x + 4, rect.centery - 1, rect.width - 8, 2)
        pygame.draw.rect(surface, (255, 255, 200), stripe)