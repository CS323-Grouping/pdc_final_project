import logging
from dataclasses import dataclass
import math
import zlib

import pygame

from network import network_handler as nw
from network import protocol
from player_scripts.animation import AnimationState, load_spritesheet_frames
from player_scripts.avatar_sprite import AVATAR_RECT, compose_player_frames, make_default_avatar
from player_scripts import player as pl
from states.common import ScreenState
from ui import components as ui
from ui.theme import DEFAULT_THEME
from world.assets import load_world_assets
from world.constants import (
    INTERNAL_HEIGHT,
    INTERNAL_WIDTH,
    PLAYER_FRAME_HEIGHT,
    PLAYER_FRAME_WIDTH,
    PLAYER_HITBOX_HEIGHT,
    PLAYER_HITBOX_WIDTH,
)
from world.level_1 import create_level_1
from world.rendering import LevelRenderer
from player_scripts import camera

LOGGER = logging.getLogger(__name__)


@dataclass
class RemotePlayer:
    position: tuple[float, float]
    animation: AnimationState


@dataclass
class AvatarAssembly:
    total_chunks: int
    payload_size: int = 0
    chunks: dict[int, bytes] = None

    def __post_init__(self):
        if self.chunks is None:
            self.chunks = {}


class InGameState(ScreenState):
    render_to_internal = True

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.hero: pl.Player | None = None
        self.platforms = []
        self._last_pos = None
        self._last_animation_state: str | None = None
        self._net_send_elapsed = 0.0
        self._name_by_id: dict[int, str] = {}
        self._remote_positions: dict[int, tuple[float, float]] = {}
        self._remote_players: dict[int, RemotePlayer] = {}
        self._elimination_feed: list[str] = []
        self._dead_sent = False
        self.world_assets = None
        self.level_renderer: LevelRenderer | None = None
        self.remote_player_image: pygame.Surface | None = None
        self.remote_frames_by_state: dict[str, list[pygame.Surface]] | None = None
        self.remote_body_frames_by_state: dict[str, list[pygame.Surface]] | None = None
        self._remote_avatar_surfaces: dict[int, pygame.Surface] = {}
        self._avatar_assemblies: dict[tuple[int, int], AvatarAssembly] = {}
        self._avatar_payload: bytes | None = None
        self._avatar_id = 0
        self._avatar_send_timer = 0.0
        self._avatar_send_count = 0
        self._paused_players: dict[int, float] = {}
        self._pause_heartbeat_elapsed = 0.0



    def enter(self):
        self.camera = camera.Camera(INTERNAL_WIDTH, INTERNAL_HEIGHT)
        self._dead_sent = False
        self._elimination_feed = []
        self._remote_positions = {}
        self._remote_players = {}
        self._remote_avatar_surfaces = {}
        self._avatar_assemblies = {}
        self._name_by_id = {pid: name for pid, _r, name in self.context.roster}
        self.world_assets = load_world_assets(self.context.project_root)
        self.level_renderer = LevelRenderer(self.world_assets)
        self.platforms = create_level_1(self.world_assets.platform_normal)
        sp = self.context.start_pos
        if isinstance(sp, (list, tuple)) and len(sp) >= 2:
            base_start = (float(sp[0]), float(sp[1]))
        else:
            base_start = (100.0, 100.0)
        start = self._spawn_position_for_local_player(base_start)
        sprite = str(
            self.context.project_root
            / "assets"
            / "player"
            / "animation"
            / "playerAnimationNormal_Blue.png"
        )
        try:
            self.hero = pl.Player(start, sprite, avatar=self.context.avatar_surface)
            remote_body_frames = load_spritesheet_frames(sprite)
            self.remote_body_frames_by_state = remote_body_frames
            self.remote_frames_by_state = compose_player_frames(remote_body_frames, make_default_avatar())
            self.remote_player_image = self.remote_frames_by_state["idle_front"][0]
        except (FileNotFoundError, pygame.error) as err:
            LOGGER.warning("Player sprite missing: %s", err)
            self.hero = None
            self.remote_player_image = None
            self.remote_frames_by_state = None
            self.remote_body_frames_by_state = None
        self._last_pos = None
        self._last_animation_state = None
        self._net_send_elapsed = 0.0
        self._avatar_payload = self._make_avatar_payload()
        self._avatar_id = zlib.adler32(self._avatar_payload) & 0xFFFF if self._avatar_payload else 0
        self._avatar_send_timer = 0.0
        self._avatar_send_count = 0
        self._paused_players = {}
        self._pause_heartbeat_elapsed = 0.0
        self._seed_remote_players_from_roster(base_start)
        self._send_initial_player_state()

    def _spawn_position_for_player(self, player_id: int, base_start: tuple[float, float]) -> tuple[float, float]:
        roster_ids = sorted(pid for pid, _ready, _name in self.context.roster)
        try:
            spawn_index = roster_ids.index(player_id)
        except ValueError:
            spawn_index = 0
        return (base_start[0] + (12.0 * spawn_index), base_start[1])

    def _spawn_position_for_local_player(self, base_start: tuple[float, float]) -> tuple[float, float]:
        net = self.context.network
        if net is None:
            return base_start
        return self._spawn_position_for_player(net.id, base_start)

    def _seed_remote_players_from_roster(self, base_start: tuple[float, float]):
        net = self.context.network
        if net is None:
            return
        for player_id, _ready, name in sorted(self.context.roster, key=lambda row: row[0]):
            spawn = self._spawn_position_for_player(player_id, base_start)
            self._name_by_id[player_id] = name
            if player_id == net.id:
                continue
            self._remote_positions[player_id] = spawn
            self._get_remote_player(player_id, spawn)

    def _send_initial_player_state(self):
        net = self.context.network
        if net is None or self.hero is None or not net.is_open:
            return
        net.update_player_state(self.hero.pos.x, self.hero.pos.y, self.hero.animation.state)
        self._last_pos = self.hero.pos.copy()
        self._last_animation_state = self.hero.animation.state

    def _make_avatar_payload(self) -> bytes | None:
        avatar = self.context.avatar_window_surface
        if avatar is None:
            return None
        network_avatar = pygame.transform.smoothscale(
            avatar,
            (protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE),
        ).convert_alpha()
        return pygame.image.tobytes(network_avatar, "RGBA")

    def _get_remote_player(self, player_id: int, position: tuple[float, float]) -> RemotePlayer | None:
        if self.hero is None:
            return None
        remote = self._remote_players.get(player_id)
        if remote is None:
            frames_by_state = self.remote_frames_by_state or self.hero.animation.frames_by_state
            remote = RemotePlayer(
                position=position,
                animation=AnimationState(frames_by_state),
            )
            self._remote_players[player_id] = remote
        else:
            remote.position = position
        return remote

    def _drain_network(self) -> bool:
        for event in self.context.drain_network_events():
            if self.handle_common_network_event(event):
                continue
            if isinstance(event, nw.PositionEvent):
                self._remote_positions[event.player_id] = (event.x, event.y)
                remote = self._get_remote_player(event.player_id, (event.x, event.y))
                if remote is not None:
                    remote.position = (event.x, event.y)
            elif isinstance(event, nw.PlayerStateEvent):
                position = (event.x, event.y)
                self._remote_positions[event.player_id] = position
                remote = self._get_remote_player(event.player_id, position)
                if remote is not None:
                    remote.animation.set_state(protocol.animation_state_name(event.animation_state_id))
            elif isinstance(event, nw.AvatarHeaderEvent):
                self._handle_avatar_header(event)
            elif isinstance(event, nw.AvatarChunkEvent):
                self._handle_avatar_chunk(event)
            elif isinstance(event, nw.MatchPauseEvent):
                self._paused_players[event.player_id] = event.seconds_remaining
                name = self._name_by_id.get(event.player_id, f"Player {event.player_id}")
                self.context.set_status(f"Match paused: {name} disconnected.", duration=2.0)
            elif isinstance(event, nw.MatchResumeEvent):
                self._paused_players.clear()
                self._pause_heartbeat_elapsed = 0.0
                self.context.set_status("Match resumed.", duration=2.0)
            elif isinstance(event, nw.EliminationEvent):
                name = self._name_by_id.get(event.player_id, f"id {event.player_id}")
                self._elimination_feed.append(f"{name} eliminated — place {event.placement}")
                self._remote_players.pop(event.player_id, None)
                self._remote_positions.pop(event.player_id, None)
                self._paused_players.pop(event.player_id, None)
            elif isinstance(event, nw.GameEndEvent):
                self.context.reset_lobby_after_game()
                self.context.results_standings = list(event.standings)
                self.context.return_state_after_results = "host_lobby" if self.context.is_host else "joined_lobby"
                self.switch("results")
                return True
            elif isinstance(event, nw.RosterEvent):
                self.context.roster = list(event.entries)
                active_ids = {pid for pid, _ready, _name in event.entries}
                for player_id in list(self._remote_positions.keys()):
                    if player_id not in active_ids:
                        self._remote_positions.pop(player_id, None)
                        self._remote_players.pop(player_id, None)
                        self._remote_avatar_surfaces.pop(player_id, None)
                for pid, _ready, name in event.entries:
                    self._name_by_id[pid] = name
        return False

    def _handle_avatar_header(self, event: nw.AvatarHeaderEvent):
        my_id = self.context.network.id if self.context.network else -1
        if event.player_id == my_id:
            return
        key = (event.player_id, event.avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            assembly = AvatarAssembly(total_chunks=event.total_chunks)
            self._avatar_assemblies[key] = assembly
        assembly.total_chunks = event.total_chunks
        assembly.payload_size = event.payload_size
        self._try_complete_avatar(event.player_id, event.avatar_id)

    def _handle_avatar_chunk(self, event: nw.AvatarChunkEvent):
        my_id = self.context.network.id if self.context.network else -1
        if event.player_id == my_id:
            return
        key = (event.player_id, event.avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            assembly = AvatarAssembly(total_chunks=event.total_chunks)
            self._avatar_assemblies[key] = assembly
        assembly.total_chunks = event.total_chunks
        assembly.chunks[event.chunk_index] = event.payload
        self._try_complete_avatar(event.player_id, event.avatar_id)

    def _try_complete_avatar(self, player_id: int, avatar_id: int):
        key = (player_id, avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            return
        if assembly.payload_size != protocol.NETWORK_AVATAR_BYTES:
            return
        if len(assembly.chunks) < assembly.total_chunks:
            return
        try:
            raw = b"".join(assembly.chunks[index] for index in range(assembly.total_chunks))
        except KeyError:
            return
        raw = raw[: assembly.payload_size]
        if len(raw) != protocol.NETWORK_AVATAR_BYTES:
            return
        try:
            avatar = pygame.image.frombytes(
                raw,
                (protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE),
                "RGBA",
            ).convert_alpha()
        except (ValueError, pygame.error):
            return
        self._remote_avatar_surfaces[player_id] = avatar
        for old_key in list(self._avatar_assemblies.keys()):
            if old_key[0] == player_id:
                self._avatar_assemblies.pop(old_key, None)

    def update(self, dt: float):
        net = self.context.network
        if net is None or self.hero is None:
            return

        if self._drain_network():
            return
        if self.machine.current_state is not self or self.context.network is not net or not net.is_open:
            return

        self._send_avatar_if_needed(dt, net)

        if self._paused_players:
            self._tick_pause(dt, net)
            return

        self.hero.update(dt, INTERNAL_WIDTH, INTERNAL_HEIGHT, self.platforms)

        for remote in self._remote_players.values():
            remote.animation.update(dt)

        if self.hero and self.camera:
            self.camera.update(self.hero)

        if not self._dead_sent and self.camera.has_fallen_below(self.hero):
            self._dead_sent = True
            net.send_dead()

        current_state = self.hero.animation.state
        self._net_send_elapsed += dt
        if (
            self._last_pos is None
            or self.hero.pos != self._last_pos
            or current_state != self._last_animation_state
            or self._net_send_elapsed >= 0.1
        ):
            net.update_player_state(self.hero.pos.x, self.hero.pos.y, current_state)
            self._last_pos = self.hero.pos.copy()
            self._last_animation_state = current_state
            self._net_send_elapsed = 0.0

    def _tick_pause(self, dt: float, net: nw.Network):
        for player_id in list(self._paused_players.keys()):
            self._paused_players[player_id] = max(0.0, self._paused_players[player_id] - dt)
        if self.hero is None:
            return
        self._pause_heartbeat_elapsed += dt
        if self._pause_heartbeat_elapsed >= 0.5:
            net.update_player_state(self.hero.pos.x, self.hero.pos.y, self.hero.animation.state)
            self._pause_heartbeat_elapsed = 0.0

    def _send_avatar_if_needed(self, dt: float, net: nw.Network):
        if self._avatar_payload is None or self._avatar_send_count >= 5:
            return
        self._avatar_send_timer -= dt
        if self._avatar_send_timer > 0:
            return
        net.send_avatar(self._avatar_id, self._avatar_payload)
        self._avatar_send_count += 1
        self._avatar_send_timer = 1.0

    def draw(self, surface):
        super().draw(surface)
        theme = DEFAULT_THEME

        camera = self.camera

        if self.hero is None:
            surface.blit(
                self.context.font.render("Missing player asset", True, theme.text_warn),
                (32, 32),
            )
            return

        if self.level_renderer is not None:
            self.level_renderer.draw_background(surface, camera)

        for platform in self.platforms:
            platform.draw(surface, camera)

        my_id = self.context.network.id if self.context.network else -1

        for p_id, p_pos in self._remote_positions.items():
            if int(p_id) == my_id:
                continue
            remote = self._remote_players.get(p_id)
            self._draw_remote_player(surface, camera, p_pos, theme, remote)

        self.hero.draw(surface, camera)

        if self.level_renderer is not None:
            self.level_renderer.draw_borders(surface)

        ui.draw_elimination_feed(
            surface,
            self.context.tiny_font,
            self._elimination_feed,
            theme
        )

    def _draw_remote_player(self, surface, camera, position, theme, remote: RemotePlayer | None = None):
        hitbox = pygame.Rect(0, 0, PLAYER_HITBOX_WIDTH, PLAYER_HITBOX_HEIGHT)
        hitbox.center = (int(round(position[0])), int(round(position[1])))
        visual_rect = pygame.Rect(0, 0, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)
        visual_rect.centerx = hitbox.centerx
        visual_rect.bottom = hitbox.bottom
        visual_rect = visual_rect.move(-int(round(camera.x)), -int(round(camera.y)))
        image = remote.animation.image if remote is not None else self.remote_player_image
        if image is None:
            hitbox = hitbox.move(-int(round(camera.x)), -int(round(camera.y)))
            pygame.draw.rect(surface, (60, 100, 220), hitbox)
            pygame.draw.rect(surface, theme.border, hitbox, width=1)
            return
        surface.blit(image, visual_rect)

    def draw_window_overlay(self, surface):
        display = self.context.display_manager
        if display is None or self.hero is None:
            return

        my_id = self.context.network.id if self.context.network else -1
        for player_id, position in self._remote_positions.items():
            if int(player_id) == my_id:
                continue
            avatar = self._remote_avatar_surfaces.get(player_id)
            remote = self._remote_players.get(player_id)
            if avatar is None or remote is None:
                continue
            visual_rect = self._visual_rect_for_position(position)
            body_image = self._remote_body_image(remote)
            self._draw_avatar_overlay(surface, avatar, visual_rect, body_image)

        avatar = self.context.avatar_window_surface
        if avatar is not None:
            visual_rect = self.hero.visual_rect()
            visual_rect = visual_rect.move(-int(round(self.camera.x)), -int(round(self.camera.y)))
            self._draw_avatar_overlay(surface, avatar, visual_rect, self.hero.body_image)

        if self._paused_players:
            self._draw_pause_overlay(surface)

    def _visual_rect_for_position(self, position: tuple[float, float]) -> pygame.Rect:
        hitbox = pygame.Rect(0, 0, PLAYER_HITBOX_WIDTH, PLAYER_HITBOX_HEIGHT)
        hitbox.center = (int(round(position[0])), int(round(position[1])))
        visual_rect = pygame.Rect(0, 0, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)
        visual_rect.centerx = hitbox.centerx
        visual_rect.bottom = hitbox.bottom
        return visual_rect.move(-int(round(self.camera.x)), -int(round(self.camera.y)))

    def _remote_body_image(self, remote: RemotePlayer) -> pygame.Surface | None:
        if self.remote_body_frames_by_state is None:
            return None
        return self.remote_body_frames_by_state[remote.animation.state][remote.animation.frame_index]

    def _draw_avatar_overlay(
        self,
        surface: pygame.Surface,
        avatar: pygame.Surface,
        visual_rect: pygame.Rect,
        body_image: pygame.Surface | None,
    ):
        display = self.context.display_manager
        if display is None:
            return
        avatar_rect = pygame.Rect(
            visual_rect.x + AVATAR_RECT.x,
            visual_rect.y + AVATAR_RECT.y,
            AVATAR_RECT.w,
            AVATAR_RECT.h,
        )
        scale = display.config.selected_scale
        target = pygame.Rect(
            avatar_rect.x * scale,
            avatar_rect.y * scale,
            avatar_rect.w * scale,
            avatar_rect.h * scale,
        )
        if not target.colliderect(surface.get_rect()):
            return
        scaled_avatar = pygame.transform.smoothscale(avatar, target.size)
        surface.blit(scaled_avatar, target)

        if body_image is None:
            return
        body_target = pygame.Rect(
            visual_rect.x * scale,
            visual_rect.y * scale,
            visual_rect.w * scale,
            visual_rect.h * scale,
        )
        if body_target.colliderect(surface.get_rect()):
            scaled_body = pygame.transform.scale(body_image, body_target.size)
            surface.blit(scaled_body, body_target)

    def _draw_pause_overlay(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        w, h = surface.get_size()
        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill((8, 10, 18, 185))
        surface.blit(scrim, (0, 0))

        box = pygame.Rect(0, 0, min(520, w - 48), 168)
        box.center = (w // 2, h // 2)
        pygame.draw.rect(surface, theme.bg_panel, box, border_radius=8)
        pygame.draw.rect(surface, theme.border_focus, box, width=2, border_radius=8)

        title = self.context.font.render("Match paused", True, theme.text)
        surface.blit(title, title.get_rect(center=(box.centerx, box.y + 36)))

        lines = []
        for player_id, remaining in sorted(self._paused_players.items()):
            name = self._name_by_id.get(player_id, f"Player {player_id}")
            lines.append(f"{name} disconnected · {max(0, math.ceil(remaining))}s to reconnect")
        if not lines:
            lines.append("Waiting for reconnect...")

        y = box.y + 72
        for line in lines[:3]:
            label = self.context.small_font.render(line, True, theme.text_muted)
            surface.blit(label, label.get_rect(center=(box.centerx, y)))
            y += 28

        hint = self.context.tiny_font.render("Gameplay is frozen for everyone.", True, theme.text_warn)
        surface.blit(hint, hint.get_rect(center=(box.centerx, box.bottom - 26)))
