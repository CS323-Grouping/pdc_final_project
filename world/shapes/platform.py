import pygame

class Platform():
    def __init__(self, size_x, size_y, pos):
        self.size_x = size_x
        self.size_y = size_y
        self.color = (0, 255, 255)
        self.pos = pygame.Vector2(pos)
        self.rect = pygame.Rect(self.pos.x, self.pos.y, self.size_x, self.size_y)


    def draw(self, surface):
        pygame.draw.rect(surface, self.color, self.rect)