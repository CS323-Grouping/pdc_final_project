import pygame


class Platform:
    def __init__(self, pos, image, collision_size=None):
        self.pos = pygame.Vector2(pos)
        self.image = image
        width = image.get_width()
        height = image.get_height()
        if collision_size is not None:
            width, height = collision_size
        self.rect = pygame.Rect(int(self.pos.x), int(self.pos.y), width, height)

    def draw(self, surface, camera=None):
        if camera is None:
            surface.blit(self.image, self.rect)
            return
        screen_rect = self.rect.move(-int(round(camera.x)), -int(round(camera.y)))
        surface.blit(self.image, screen_rect)
