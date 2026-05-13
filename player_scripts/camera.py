import pygame


class Camera:
    def __init__(self, width, height, upper_follow_threshold=64, fall_margin=32):
        self.x = 0.0
        self.y = 0.0
        self.width = width
        self.height = height
        self.upper_follow_threshold = upper_follow_threshold
        self.fall_margin = fall_margin
        self.SCREEN_WIDTH = width
        self.SCREEN_HEIGHT = height

    @property
    def camera_rect(self):
        return pygame.Rect(
            int(round(-self.x)),
            int(round(-self.y)),
            self.width,
            self.height,
        )

    @property
    def bottom(self):
        return self.y + self.height

    def apply(self, entity):
        return entity.rect.move(-int(round(self.x)), -int(round(self.y)))

    def update(self, target):
        target_screen_y = target.rect.centery - self.y
        if target_screen_y < self.upper_follow_threshold:
            target_y = target.rect.centery - self.upper_follow_threshold
            self.y = min(self.y, target_y)

    def has_fallen_below(self, target) -> bool:
        return target.rect.top > self.bottom + self.fall_margin
