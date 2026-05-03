import pygame


class Player:
    def __init__(self, start_pos, image_path, color=(255, 0, 255)):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.vel = pygame.Vector2(0, 0)
        self.pos = pygame.Vector2(start_pos)
        self.speed = 300
        self.gravity = 1800.0
        self.jump_velocity = -720.0
        self.rect = pygame.Rect(0, 0, 64, 128)
        self.rect.center = (int(self.pos.x), int(self.pos.y))
        self.on_ground = False
        self.color = color
        self._w_down_prev = False

    def _sync_rect_from_pos(self):
        self.rect.center = (int(round(self.pos.x)), int(round(self.pos.y)))

    def check_border(self, screen_width, screen_height):
        if self.pos.x < 0:
            self.pos.x = 0
        if self.pos.x > screen_width:
            self.pos.x = screen_width
        if self.pos.y < 0:
            self.pos.y = 0
        if self.pos.y > screen_height:
            self.pos.y = screen_height

    def handle_input(self, dt, screen_width, screen_height):
        keys = pygame.key.get_pressed()
        w_down = keys[pygame.K_w]
        w_pressed_edge = w_down and not self._w_down_prev
        self._w_down_prev = w_down

        direction = pygame.Vector2(0, 0)
        if keys[pygame.K_a]:
            direction.x -= 1
        if keys[pygame.K_d]:
            direction.x += 1
        if direction.length() > 0:
            direction = direction.normalize()

        self.pos.x += direction.x * self.speed * dt
        # self.check_border(screen_width, screen_height)

        if w_pressed_edge and self.on_ground:
            self.vel.y = self.jump_velocity
            self.on_ground = False

    def _supported_on_platform_top(self, platforms) -> bool:
        """Feet sit on a platform surface (horizontal overlap + small vertical band)."""
        for p in platforms:
            overlap_x = min(self.rect.right, p.rect.right) - max(self.rect.left, p.rect.left)
            if overlap_x <= 2:
                continue
            dy = self.rect.bottom - p.rect.top
            if 0 <= dy <= 10:
                return True
        return False

    def _resolve_platforms_horizontal(self, platforms):
        """Side collisions so the player cannot walk through platform edges."""
        self._sync_rect_from_pos()
        for _ in range(4):
            moved = False
            for p in platforms:
                if not self.rect.colliderect(p.rect):
                    continue
                pen_l = self.rect.right - p.rect.left
                pen_r = p.rect.right - self.rect.left
                if pen_l <= 0 or pen_r <= 0:
                    continue
                if pen_l < pen_r:
                    self.rect.right = p.rect.left
                    moved = True
                elif pen_r < pen_l:
                    self.rect.left = p.rect.right
                    moved = True
                else:
                    if self.rect.centerx < p.rect.centerx:
                        self.rect.right = p.rect.left
                    else:
                        self.rect.left = p.rect.right
                    moved = True
                self.pos.x = float(self.rect.centerx)
            if not moved:
                break

    def _resolve_platforms_vertical(self, platforms):
        """Top (land) and bottom (bonk) collision after vertical move."""
        self._sync_rect_from_pos()
        self.on_ground = False
        for _ in range(4):
            moved = False
            for p in platforms:
                if not self.rect.colliderect(p.rect):
                    continue
                pen_bottom = self.rect.bottom - p.rect.top
                pen_top = p.rect.bottom - self.rect.top
                if pen_bottom <= 0 or pen_top <= 0:
                    continue
                if pen_bottom < pen_top:
                    if self.vel.y >= -1.0:
                        self.rect.bottom = p.rect.top
                        self.pos.y = float(self.rect.centery)
                        self.vel.y = 0
                        self.on_ground = True
                        moved = True
                elif pen_top < pen_bottom:
                    if self.vel.y <= 0:
                        self.rect.top = p.rect.bottom
                        self.pos.y = float(self.rect.centery)
                        self.vel.y = 0
                        moved = True
                else:
                    if self.vel.y >= 0:
                        self.rect.bottom = p.rect.top
                        self.pos.y = float(self.rect.centery)
                        self.vel.y = 0
                        self.on_ground = True
                    else:
                        self.rect.top = p.rect.bottom
                        self.pos.y = float(self.rect.centery)
                        self.vel.y = 0
                    moved = True
            if not moved:
                break

    def update(self, dt, screen_width, screen_height, entities):
        self.handle_input(dt, screen_width, screen_height)

        self._resolve_platforms_horizontal(entities)

        if self.on_ground and not self._supported_on_platform_top(entities):
            self.on_ground = False

        if not self.on_ground:
            self.vel.y += self.gravity * dt

        self.pos.y += self.vel.y * dt
        # self.check_border(screen_width, screen_height)

        self._resolve_platforms_vertical(entities)
        self._sync_rect_from_pos()

    def draw(self, surface):
        pygame.draw.rect(surface, self.color, self.rect)
