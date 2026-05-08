import pygame
import random

from player_scripts.animation import AnimationState, load_spritesheet_frames
from player_scripts.avatar_sprite import compose_player_frames, make_default_avatar
from world.constants import (
    PLAYABLE_RIGHT,
    PLAYABLE_X,
    PLAYER_FRAME_HEIGHT,
    PLAYER_FRAME_WIDTH,
    PLAYER_GRAVITY,
    PLAYER_HITBOX_HEIGHT,
    PLAYER_HITBOX_WIDTH,
    PLAYER_JUMP_VELOCITY,
    PLAYER_MOVE_SPEED,
)

# Launch boost: ghost through platforms while ascending; overlap escape afterwards (apex = vel.y near zero).
LAUNCH_PHASE_APEX_EPS = 0.5
LAUNCH_OVERLAP_NUDGE_PX = 2

# Slippery ice: how fast horizontal momentum ramps up (higher = snappier start, less "slow motion").
SLIPPERY_ACCEL_SCALE = 3.25


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
        self.speed = PLAYER_MOVE_SPEED
        self.gravity = PLAYER_GRAVITY
        self.jump_velocity = PLAYER_JUMP_VELOCITY
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
        self.speed_boost_timer = 0.0
        self.speed_boost = 1.0
        self.jump_boost_timer = 0.0
        self.jump_boost = 1.0
        self.shield_timer = 0.0
        self.double_jump_timer = 0.0
        self.has_double_jumped = False
        self.reverse_control_timer = 0.0
        self.slippery_timer = 0.0
        self.slippery_boost = 1.0
        self.slow_falling_timer = 0.0
        self.heavy_timer = 0.0
        self.launch_timer = 0.0
        self.weak_jump_timer = 0.0

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

        # Apply debuffs
        if self.reverse_control_timer > 0:
            direction.x *= -1
        if self.slippery_timer > 0:
            self.slippery_boost = 0.8  # Slower movement for slippery debuff
        else:
            self.slippery_boost = 1.0
        if self._move_dir == 0:
            self._idle_timer += dt
        else:
            self._idle_timer = 0.0

        self.pos.x += direction.x * self.speed * self.speed_boost * self.slippery_boost * dt
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

    def _any_platform_overlap(self, platforms) -> bool:
        return any(self.rect.colliderect(p.rect) for p in platforms)

    def _launch_platform_collision_mode(self, platforms) -> tuple[bool, str | None]:
        """Return (skip_platform_solids, mode) with mode \"ascent\", \"escape\", or None."""
        ascend = self.launch_timer > 0 and self.vel.y < -LAUNCH_PHASE_APEX_EPS
        if ascend:
            return True, "ascent"

        overlap = self._any_platform_overlap(platforms)
        overlap_escape_needed = overlap and (
            (self.launch_timer > 0 and self.vel.y >= -LAUNCH_PHASE_APEX_EPS)
            or self._launch_overlap_escape
        )
        if overlap_escape_needed:
            self._launch_overlap_escape = True
            return True, "escape"

        self._launch_overlap_escape = False
        return False, None

    def _launch_overlap_centroid_nudge(self, platforms) -> None:
        """Small separation when stuck overlapping after apex; favors down when tied."""
        overlapping = [p for p in platforms if self.rect.colliderect(p.rect)]
        if not overlapping:
            return
        score = sum(1 if self.rect.centery > p.rect.centery else -1 for p in overlapping)
        if score > 0:
            dy = LAUNCH_OVERLAP_NUDGE_PX
        elif score < 0:
            dy = -LAUNCH_OVERLAP_NUDGE_PX
        else:
            dy = LAUNCH_OVERLAP_NUDGE_PX
        self.pos.y += dy
        self._sync_rect_from_pos()
        self._clamp_to_playable_width()

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

        skip_solids_horizontal, _ = self._launch_platform_collision_mode(entities)

        if not skip_solids_horizontal:
            self._resolve_platforms_horizontal(entities)

        if not skip_solids_horizontal and self.vel.y >= 0 and self._supported_on_platform_top(entities):
            self._snap_to_supported_platform_top(entities)
        elif self.on_ground and not skip_solids_horizontal:
            self.on_ground = False
            self._set_air_animation_from_ground_state()

        if self.on_ground:
            self._coyote_timer = self.COYOTE_SECONDS
            self.has_double_jumped = False
        else:
            self._coyote_timer = max(0.0, self._coyote_timer - dt)

        if self._jump_buffer > 0 and (self.on_ground or self._coyote_timer > 0):
            self._start_jump()
        elif self._jump_buffer > 0 and not self.on_ground and not self.has_double_jumped and self.double_jump_timer > 0:
            self._start_double_jump()

        if not self.on_ground:
            gravity_modifier = 1.0
            if self.vel.y > 0:  # Only apply gravity modifiers when falling
                if self.slow_falling_timer > 0:
                    gravity_modifier = 0.5
                elif self.heavy_timer > 0:
                    gravity_modifier = 1.5
            self.vel.y += self.gravity * gravity_modifier * dt

        self.pos.y += self.vel.y * dt

        if self.launch_timer <= 0:
            self._resolve_platforms_vertical(entities)
        self._sync_rect_from_pos()
        if not self.on_ground and self.vel.y >= 0 and self.launch_timer <= 0:
            self._snap_to_supported_platform_top(entities)
        self._select_animation_state()
        self.animation.update(dt)
        self.image = self.animation.image

        # Update power up timers
        self.speed_boost_timer = max(0.0, self.speed_boost_timer - dt)
        if self.speed_boost_timer == 0:
            self.speed_boost = 1.0

        self.jump_boost_timer = max(0.0, self.jump_boost_timer - dt)
        if self.jump_boost_timer == 0:
            self.jump_boost = 1.0

        self.shield_timer = max(0.0, self.shield_timer - dt)

        self.double_jump_timer = max(0.0, self.double_jump_timer - dt)

        self.reverse_control_timer = max(0.0, self.reverse_control_timer - dt)

        self.slippery_timer = max(0.0, self.slippery_timer - dt)

        self.slow_falling_timer = max(0.0, self.slow_falling_timer - dt)

        self.heavy_timer = max(0.0, self.heavy_timer - dt)

        self.launch_timer = max(0.0, self.launch_timer - dt)

        self.weak_jump_timer = max(0.0, self.weak_jump_timer - dt)

    def _start_jump(self):
        self._set_air_animation_from_ground_state()
        jump_modifier = 1.0
        if self.weak_jump_timer > 0:
            jump_modifier = 0.5  # Weaker jump
        self.vel.y = self.jump_velocity * self.jump_boost * jump_modifier
        self.on_ground = False
        self._coyote_timer = 0.0
        self._jump_buffer = 0.0
        self.has_double_jumped = False
        self.animation.set_state(self._air_animation_state)

    def _start_double_jump(self):
        self.vel.y = self.jump_velocity * 1.25  # Slightly stronger double jump
        self.has_double_jumped = True
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

    def collect_power_up(self, effect_type):
        if effect_type == 'orb':
            effect_type = random.choice([
                'speed', 'jump', 'shield', 'double_jump', 'launch',
                'reverse_control', 'slippery', 'slow_falling', 'heavy', 'weak_jump'
            ])

        debuffs = {'reverse_control', 'slippery', 'slow_falling', 'heavy', 'weak_jump'}
        if effect_type in debuffs and self.shield_timer > 0:
            self.shield_timer = 0.0
            return 'shield_blocked'

        if effect_type == 'speed':
            self.speed_boost_timer = 3.0
            self.speed_boost = 1.5
        elif effect_type == 'jump':
            self.jump_boost_timer = 3.0
            self.jump_boost = 1.5
        elif effect_type == 'shield':
            self.shield_timer = 15.0
        elif effect_type == 'double_jump':
            self.double_jump_timer = 3.0
        elif effect_type == 'launch':
            self.vel.y = -520.0  # Stronger launch upward
            self.launch_timer = 1.0  # Bypass platforms for 1 second
        elif effect_type == 'reverse_control':
            self.shield_timer = 0.0
            self.reverse_control_timer = 5.0
        elif effect_type == 'slippery':
            self.shield_timer = 0.0
            self.slippery_timer = 5.0
        elif effect_type == 'slow_falling':
            self.shield_timer = 0.0
            self.slow_falling_timer = 5.0
        elif effect_type == 'heavy':
            self.shield_timer = 0.0
            self.heavy_timer = 5.0
        elif effect_type == 'weak_jump':
            self.shield_timer = 0.0
            self.weak_jump_timer = 2.0

        return effect_type

    def active_power_up_timers(self) -> dict[str, float]:
        timers = {}
        if self.speed_boost_timer > 0:
            timers['Speed Buff'] = self.speed_boost_timer
        if self.jump_boost_timer > 0:
            timers['Jump Buff'] = self.jump_boost_timer
        if self.shield_timer > 0:
            timers['Shield Aura'] = self.shield_timer
        if self.double_jump_timer > 0:
            timers['Double Jump'] = self.double_jump_timer
        if self.launch_timer > 0:
            timers['Launch'] = self.launch_timer
        if self.reverse_control_timer > 0:
            timers['Reverse Control'] = self.reverse_control_timer
        if self.slippery_timer > 0:
            timers['Slippery'] = self.slippery_timer
        if self.slow_falling_timer > 0:
            timers['Slow Falling'] = self.slow_falling_timer
        if self.heavy_timer > 0:
            timers['Heavy'] = self.heavy_timer
        if self.weak_jump_timer > 0:
            timers['Weak Jump'] = self.weak_jump_timer
        return timers

    def draw(self, surface, camera=None):
        rect = self.visual_rect()
        if camera is not None:
            rect = rect.move(-int(round(camera.x)), -int(round(camera.y)))
        surface.blit(self.image, rect)
        if self.shield_timer > 0:
            center = rect.center
            pygame.draw.circle(surface, (0, 255, 255), center, 30, 2)  # Cyan aura for shield
