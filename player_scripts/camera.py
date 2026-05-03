import pygame

class Camera:
    def __init__(self, width, height):
        self.camera_rect = pygame.Rect(0, 0, width, height)
        self.SCREEN_WIDTH = width
        self.SCREEN_HEIGHT = height

    def apply(self, entity):
        return entity.rect.move(self.camera_rect.topleft)

    def update(self, target):
        x = -target.rect.centerx + self.SCREEN_WIDTH // 2
        y = -target.rect.centery + self.SCREEN_HEIGHT // 2

        self.camera_rect = pygame.Rect(x, y, self.camera_rect.width, self.camera_rect.height)