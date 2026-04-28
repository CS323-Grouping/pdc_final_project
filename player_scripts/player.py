import pygame
class Player:
    def __init__(self, start_pos, image_path, color=(255,0,255)):
        self.image = pygame.image.load(image_path).convert_alpha()
        # self.image = pygame.transform.scale(self.image, (self.image.get_height()*0.27, 128))
        self.vel = pygame.Vector2(0, 0)
        self.pos = pygame.Vector2(start_pos)
        self.speed = 300
        self.rect = pygame.Rect(start_pos, (64, 128))
        self.on_ground = False
        self.color = color

    def handle_input(self, dt):
        keys = pygame.key.get_pressed()

        direction = pygame.Vector2(0, 0)

        if keys[pygame.K_a]:
            direction.x -= 1
        if keys[pygame.K_d]:
            direction.x += 1

        if direction.length() > 0:
            direction = direction.normalize()

        self.pos.x += direction.x * self.speed * dt
        if keys[pygame.K_w] and self.on_ground:
            self.vel.y = -12
            self.on_ground = False

    def check_border(self, screen_width, screen_height):
        if self.pos.x > screen_width: self.pos.x = screen_width
        if self.pos.x < 0: self.pos.x = 0
        if self.pos.y > screen_height: self.pos.y = screen_height
        if self.pos.y < 0: self.pos.y = 0

    def update(self, dt, screen_width, screen_height, entities):
        self.handle_input(dt)
        self.check_border(screen_width, screen_height)

        if not self.on_ground:
            self.vel.y += 0.5

        self.pos.y += self.vel.y

        self.rect.center = self.pos

        self.on_ground = False

        for entity in entities:
            if self.rect.colliderect(entity.rect):

                if self.vel.y > 0 and self.rect.bottom <= entity.rect.bottom:
                    self.rect.bottom = entity.rect.top
                    self.pos.y = self.rect.centery
                    self.vel.y = 0
                    self.on_ground = True

                elif self.vel.y < 0:
                    self.rect.top = entity.rect.bottom
                    self.pos.y = self.rect.centery
                    self.vel.y = 0



    def draw(self, surface):
        # surface.blit(self.image, self.rect) # Only change if there is sprite for the player already
        pygame.draw.rect(surface, self.color, self.rect)

