import pygame

from player_scripts.animation import AnimationState, load_spritesheet_frames
from player_scripts.avatar_sprite import compose_player_frames, make_default_avatar
from world.constants import (
    PLAYABLE_RIGHT,
    PLAYABLE_X,
    PLAYER_FRAME_HEIGHT,
    PLAYER_FRAME_WIDTH,
    PLAYER_HITBOX_HEIGHT,
    PLAYER_HITBOX_WIDTH,
)


class Player:
    IDLE_DEBOUNCE_SECONDS = 0.1
    JUMP_BUFFER_SECONDS = 0.12
    COYOTE_SECONDS = 0.1

    def __init__(self, start_pos, spritesheet_path, avatar=None, color=(255, 0, 255)):
        body_frames = load_spritesheet_frames(spritesheet_path)
        self.body_frames_by_state = body_frames
        avatar_surface = avatar if avatar is not None else make_default_avatar()
        self.animation = AnimationState(compose_player_frames(body_frames, avatar_surface))
        self.image = self.animation.image
        self.vel = pygame.Vector2(0, 0)
        self.pos = pygame.Vector2(start_pos)
        self.speed = 90.0
        self.gravity = 520.0
        self.jump_velocity = -220.0
        self.rect = pygame.Rect(0, 0, PLAYER_HITBOX_WIDTH, PLAYER_HITBOX_HEIGHT)
        self.rect.center = (int(self.pos.x), int(self.pos.y))
        self.on_ground = False
        self.color = color
        self._w_down_prev = False
        self._move_dir = 0
        self._idle_timer = self.IDLE_DEBOUNCE_SECONDS
        self._jump_buffer = 0.0
        self._coyote_timer = 0.0
        self._air_animation_state = "jump_front"

    def _sync_rect_from_pos(self):
        self.rect.center = (int(round(self.pos.x)), int(round(self.pos.y)))

    def _clamp_to_playable_width(self):
        half_width = self.rect.width / 2
        self.pos.x = max(PLAYABLE_X + half_width, min(PLAYABLE_RIGHT - half_width, self.pos.x))
        self._sync_rect_from_pos()

    def handle_input(self, dt, screen_width, screen_height):
        _ = screen_width, screen_height
        keys = pygame.key.get_pressed()
        w_down = keys[pygame.K_w]
        w_pressed_edge = w_down and not self._w_down_prev
        self._w_down_prev = w_down
        if w_pressed_edge:
            self._jump_buffer = self.JUMP_BUFFER_SECONDS
        elif self._jump_buffer > 0:
            self._jump_buffer = max(0.0, self._jump_buffer - dt)

        direction = pygame.Vector2(0, 0)
        if keys[pygame.K_a]:
            direction.x -= 1
        if keys[pygame.K_d]:
            direction.x += 1
        if direction.length() > 0:
            direction = direction.normalize()
        self._move_dir = int(direction.x)
        if self._move_dir == 0:
            self._idle_timer += dt
        else:
            self._idle_timer = 0.0

        self.pos.x += direction.x * self.speed * dt
        self._clamp_to_playable_width()

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

    def _snap_to_supported_platform_top(self, platforms) -> bool:
        """Keep exact top contact grounded even when rects only touch, not overlap."""
        best_top = None
        for p in platforms:
            overlap_x = min(self.rect.right, p.rect.right) - max(self.rect.left, p.rect.left)
            if overlap_x <= 2:
                continue
            dy = self.rect.bottom - p.rect.top
            if 0 <= dy <= 10 and (best_top is None or p.rect.top < best_top):
                best_top = p.rect.top
        if best_top is None:
            return False
        self.rect.bottom = best_top
        self.pos.y = float(self.rect.centery)
        self.vel.y = 0.0
        self.on_ground = True
        return True

    def _set_air_animation_from_ground_state(self):
        previous_state = self.animation.state
        if previous_state == "walk_left":
            self._air_animation_state = "jump_left"
        elif previous_state == "walk_right":
            self._air_animation_state = "jump_right"
        elif previous_state == "idle_front":
            self._air_animation_state = "jump_front"
        elif self._move_dir < 0:
            self._air_animation_state = "jump_left"
        elif self._move_dir > 0:
            self._air_animation_state = "jump_right"
        else:
            self._air_animation_state = "jump_front"

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
                self._clamp_to_playable_width()
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

        if self.vel.y >= 0 and self._supported_on_platform_top(entities):
            self._snap_to_supported_platform_top(entities)
        elif self.on_ground:
            self.on_ground = False
            self._set_air_animation_from_ground_state()

        if self.on_ground:
            self._coyote_timer = self.COYOTE_SECONDS
        else:
            self._coyote_timer = max(0.0, self._coyote_timer - dt)

        if self._jump_buffer > 0 and (self.on_ground or self._coyote_timer > 0):
            self._start_jump()

        if not self.on_ground:
            self.vel.y += self.gravity * dt

        self.pos.y += self.vel.y * dt

        self._resolve_platforms_vertical(entities)
        self._sync_rect_from_pos()
        if not self.on_ground and self.vel.y >= 0:
            self._snap_to_supported_platform_top(entities)
        self._select_animation_state()
        self.animation.update(dt)
        self.image = self.animation.image

    def _start_jump(self):
        self._set_air_animation_from_ground_state()
        self.vel.y = self.jump_velocity
        self.on_ground = False
        self._coyote_timer = 0.0
        self._jump_buffer = 0.0
        self.animation.set_state(self._air_animation_state)

    def _select_animation_state(self):
        if not self.on_ground:
            self.animation.set_state(self._air_animation_state)
            return
        if self._move_dir < 0:
            self.animation.set_state("walk_left")
        elif self._move_dir > 0:
            self.animation.set_state("walk_right")
        elif self._idle_timer >= self.IDLE_DEBOUNCE_SECONDS:
            self.animation.set_state("idle_front")

    def visual_rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)
        rect.centerx = self.rect.centerx
        rect.bottom = self.rect.bottom
        return rect

    @property
    def body_image(self) -> pygame.Surface:
        return self.body_frames_by_state[self.animation.state][self.animation.frame_index]

    def draw(self, surface, camera=None):
        rect = self.visual_rect()
        if camera is not None:
            rect = rect.move(-int(round(camera.x)), -int(round(camera.y)))
        surface.blit(self.image, rect)
