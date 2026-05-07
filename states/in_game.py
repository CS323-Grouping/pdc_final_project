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
    BORDER_WIDTH,
    INTERNAL_HEIGHT,
    INTERNAL_WIDTH,
    PLAYABLE_RIGHT,
    PLAYER_FRAME_HEIGHT,
    PLAYER_FRAME_WIDTH,
    PLAYER_HITBOX_HEIGHT,
    PLAYER_HITBOX_WIDTH,
)
from world.level_1 import create_level_1, LEVEL_1_GOAL_CENTER_X, LEVEL_1_GOAL_Y
from world.rendering import LevelRenderer
from world.shapes.goal import Goal
from player_scripts import camera

LOGGER = logging.getLogger(__name__)


@dataclass
class RemotePlayer:
    position: tuple[float, float]
    animation: AnimationState
    body_frames_by_state: dict[str, list[pygame.Surface]]


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
        self._remote_model_frames_cache: dict[tuple[str, str], dict[str, list[pygame.Surface]]] = {}
        self._remote_models: dict[int, tuple[str, str]] = {}
        self._remote_avatar_surfaces: dict[int, pygame.Surface] = {}
        self._avatar_assemblies: dict[tuple[int, int], AvatarAssembly] = {}
        self._avatar_payload: bytes | None = None
        self._avatar_id = 0
        self._avatar_send_timer = 0.0
        self._avatar_send_count = 0
        self._paused_players: dict[int, float] = {}
        self._pause_heartbeat_elapsed = 0.0
        self._observing = False
        self._spectate_player_id: int | None = None
        self._spectate_snap_pending = False
        self._placements_by_id: dict[int, int] = {}
        self.goal: Goal | None = None
        self._goal_reached = False



    def enter(self):
        self.camera = camera.Camera(INTERNAL_WIDTH, INTERNAL_HEIGHT)
        self._dead_sent = False
        self._elimination_feed = []
        self._remote_positions = {}
        self._remote_players = {}
        self._remote_avatar_surfaces = {}
        self._remote_models = {}
        self._remote_model_frames_cache = {}
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
        sprite = str(self.context.player_animation_path())
        try:
            self.hero = pl.Player(start, sprite, avatar=self.context.current_avatar_frame())
            remote_body_frames = load_spritesheet_frames(sprite)
            self.remote_body_frames_by_state = remote_body_frames
            self.remote_frames_by_state = compose_player_frames(remote_body_frames, make_default_avatar(self.context.project_root))
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
        self._observing = False
        self._spectate_player_id = None
        self._spectate_snap_pending = False
        self._placements_by_id = {}
        self.goal = Goal(LEVEL_1_GOAL_CENTER_X, LEVEL_1_GOAL_Y)
        self._goal_reached = False
        self._seed_remote_players_from_roster(base_start)
        self._send_initial_player_state()

    def handle_event(self, event):
        super().handle_event(event)
        if not self._observing or self._paused_players:
            return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                self._cycle_spectator_target(1)
                return
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self._cycle_spectator_target(-1)
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            prev_rect, next_rect = self._spectator_control_rects()
            if prev_rect.collidepoint(event.pos):
                self._cycle_spectator_target(-1)
                return
            if next_rect.collidepoint(event.pos):
                self._cycle_spectator_target(1)
                return

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
        avatar = self.context.current_avatar_source()
        network_avatar = pygame.transform.smoothscale(
            avatar,
            (protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE),
        ).convert_alpha()
        return pygame.image.tobytes(network_avatar, "RGBA")

    def _body_frames_for_model(self, model_type: str, model_color: str) -> dict[str, list[pygame.Surface]]:
        key = (
            protocol.normalize_model_type(model_type),
            protocol.normalize_model_color(model_color),
        )
        frames = self._remote_model_frames_cache.get(key)
        if frames is not None:
            return frames
        try:
            frames = load_spritesheet_frames(self.context.player_animation_path(*key))
        except (FileNotFoundError, pygame.error):
            if self.remote_body_frames_by_state is not None:
                return self.remote_body_frames_by_state
            raise
        self._remote_model_frames_cache[key] = frames
        return frames

    def _remote_model_for_player(self, player_id: int) -> tuple[str, str]:
        return self._remote_models.get(player_id, (protocol.DEFAULT_MODEL_TYPE, protocol.DEFAULT_MODEL_COLOR))

    def _rebuild_remote_player_model(self, player_id: int):
        remote = self._remote_players.get(player_id)
        if remote is None:
            return
        state = remote.animation.state
        frame_index = remote.animation.frame_index
        model_type, model_color = self._remote_model_for_player(player_id)
        body_frames = self._body_frames_for_model(model_type, model_color)
        frames = compose_player_frames(body_frames, make_default_avatar(self.context.project_root))
        remote.body_frames_by_state = body_frames
        remote.animation = AnimationState(frames)
        if state in frames:
            remote.animation.state = state
            remote.animation.frame_index = min(frame_index, len(frames[state]) - 1)

    def _get_remote_player(self, player_id: int, position: tuple[float, float]) -> RemotePlayer | None:
        if self.hero is None:
            return None
        remote = self._remote_players.get(player_id)
        if remote is None:
            model_type, model_color = self._remote_model_for_player(player_id)
            try:
                body_frames = self._body_frames_for_model(model_type, model_color)
            except (FileNotFoundError, pygame.error):
                body_frames = self.remote_body_frames_by_state or self.hero.body_frames_by_state
            frames_by_state = compose_player_frames(body_frames, make_default_avatar(self.context.project_root))
            remote = RemotePlayer(
                position=position,
                animation=AnimationState(frames_by_state),
                body_frames_by_state=body_frames,
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
                if event.player_id in self._placements_by_id:
                    continue
                self._remote_positions[event.player_id] = (event.x, event.y)
                remote = self._get_remote_player(event.player_id, (event.x, event.y))
                if remote is not None:
                    remote.position = (event.x, event.y)
            elif isinstance(event, nw.PlayerStateEvent):
                if event.player_id in self._placements_by_id:
                    continue
                position = (event.x, event.y)
                self._remote_positions[event.player_id] = position
                remote = self._get_remote_player(event.player_id, position)
                if remote is not None:
                    remote.animation.set_state(protocol.animation_state_name(event.animation_state_id))
            elif isinstance(event, nw.AvatarHeaderEvent):
                old_model = self._remote_models.get(event.player_id)
                self._remote_models[event.player_id] = (event.model_type, event.model_color)
                if old_model != self._remote_models[event.player_id]:
                    self._rebuild_remote_player_model(event.player_id)
                self._handle_avatar_header(event)
            elif isinstance(event, nw.AvatarChunkEvent):
                self._handle_avatar_chunk(event)
            elif isinstance(event, nw.MatchPauseEvent):
                self._paused_players[event.player_id] = event.seconds_remaining
                name = self._name_by_id.get(event.player_id, f"Player {event.player_id}")
                LOGGER.info(
                    "Match pause received player_id=%s name=%s remaining=%.2f",
                    event.player_id,
                    name,
                    event.seconds_remaining,
                )
                self.context.set_status(f"Match paused: {name} disconnected.", duration=2.0)
            elif isinstance(event, nw.MatchResumeEvent):
                self._paused_players.clear()
                self._pause_heartbeat_elapsed = 0.0
                LOGGER.info("Match resume received")
                self.context.set_status("Match resumed.", duration=2.0)
            elif isinstance(event, nw.EliminationEvent):
                name = self._name_by_id.get(event.player_id, f"id {event.player_id}")
                LOGGER.info("Elimination received player_id=%s name=%s placement=%s", event.player_id, name, event.placement)
                self._elimination_feed.append(f"{name} eliminated — place {event.placement}")
                self._placements_by_id[event.player_id] = event.placement
                my_id = self.context.network.id if self.context.network else -1
                if event.player_id == my_id:
                    self._observing = True
                    self._dead_sent = True
                    self._set_spectator_target(self._default_spectator_target(), snap=True)
                    LOGGER.info("Local player eliminated; switched to observing player_id=%s", event.player_id)
                    self.context.set_status("Eliminated. Observing the remaining players.", duration=3.0)
                else:
                    self._remote_players.pop(event.player_id, None)
                    self._remote_positions.pop(event.player_id, None)
                    self._remote_avatar_surfaces.pop(event.player_id, None)
                    self._remote_models.pop(event.player_id, None)
                    if self._spectate_player_id == event.player_id:
                        self._set_spectator_target(self._default_spectator_target(), snap=True)
                self._paused_players.pop(event.player_id, None)
            elif isinstance(event, nw.GameEndEvent):
                LOGGER.info("Game end received reason=%s standings=%s", event.reason_code, event.standings)
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
                        self._remote_models.pop(player_id, None)
                        if self._spectate_player_id == player_id:
                            self._set_spectator_target(self._default_spectator_target(), snap=True)
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

        if self._observing:
            self._tick_observer(dt)
            return

        self.hero.update(dt, INTERNAL_WIDTH, INTERNAL_HEIGHT, self.platforms)

        for remote in self._remote_players.values():
            remote.animation.update(dt)

        if self.goal is not None:
            self.goal.update(dt)

        if self.hero and self.camera:
            self.camera.update(self.hero)

        if not self._dead_sent and self.camera.has_fallen_below(self.hero):
            self._dead_sent = True
            LOGGER.info("Local player fell below camera; sending DEAD")
            net.send_dead()

        if (
            not self._goal_reached
            and not self._dead_sent
            and self.goal is not None
            and self.hero.rect.colliderect(self.goal.rect)
        ):
            self._goal_reached = True
            self._observing = True
            self._set_spectator_target(self._default_spectator_target(), snap=True)
            LOGGER.info("Local player reached goal; sending GOAL and observing")
            net.send_goal()

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

    def _tick_observer(self, dt: float):
        for remote in self._remote_players.values():
            remote.animation.update(dt)
        if self.goal is not None:
            self.goal.update(dt)
        if self.camera is None:
            return
        focus = self._observer_focus_position()
        if focus is None:
            return
        self._update_observer_camera(focus, dt)

    def _alive_spectator_ids(self) -> list[int]:
        my_id = self.context.network.id if self.context.network else -1
        ids = [
            player_id
            for player_id in self._remote_positions
            if player_id != my_id and player_id not in self._placements_by_id
        ]
        return sorted(ids, key=lambda player_id: self._name_by_id.get(player_id, f"P{player_id}").lower())

    def _default_spectator_target(self) -> int | None:
        alive_ids = self._alive_spectator_ids()
        if not alive_ids:
            return None
        return min(alive_ids, key=lambda player_id: self._remote_positions[player_id][1])

    def _set_spectator_target(self, player_id: int | None, snap: bool = False):
        if player_id == self._spectate_player_id:
            self._spectate_snap_pending = self._spectate_snap_pending or snap
            return
        self._spectate_player_id = player_id
        self._spectate_snap_pending = snap
        if player_id is None:
            LOGGER.info("Spectator target cleared")
            return
        LOGGER.info(
            "Spectator target set player_id=%s name=%s snap=%s",
            player_id,
            self._name_by_id.get(player_id, f"P{player_id}"),
            snap,
        )

    def _cycle_spectator_target(self, direction: int):
        alive_ids = self._alive_spectator_ids()
        if not alive_ids:
            self._set_spectator_target(None, snap=True)
            return
        if self._spectate_player_id not in alive_ids:
            self._set_spectator_target(self._default_spectator_target(), snap=True)
            return
        index = alive_ids.index(self._spectate_player_id)
        self._set_spectator_target(alive_ids[(index + direction) % len(alive_ids)], snap=True)

    def _observer_focus_position(self) -> tuple[float, float] | None:
        alive_ids = self._alive_spectator_ids()
        if not alive_ids:
            self._set_spectator_target(None, snap=True)
        elif self._spectate_player_id not in alive_ids:
            self._set_spectator_target(self._default_spectator_target(), snap=True)
        if self._spectate_player_id is not None:
            position = self._remote_positions.get(self._spectate_player_id)
            if position is not None:
                return position
        if self.hero is not None:
            return (self.hero.pos.x, self.hero.pos.y)
        return None

    def _update_observer_camera(self, focus: tuple[float, float], dt: float):
        if self.camera is None:
            return
        target_y = min(0.0, focus[1] - self.camera.upper_follow_threshold)
        if self._spectate_snap_pending:
            self.camera.y = target_y
            self._spectate_snap_pending = False
            return
        follow = min(1.0, dt * 12.0)
        self.camera.y += (target_y - self.camera.y) * follow

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
        net.send_avatar(self._avatar_id, self._avatar_payload, self.context.model_type, self.context.model_color)
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

        if self.goal is not None:
            self.goal.draw(surface, camera)

        my_id = self.context.network.id if self.context.network else -1

        for p_id, p_pos in self._remote_positions.items():
            if int(p_id) == my_id:
                continue
            remote = self._remote_players.get(p_id)
            self._draw_remote_player(surface, camera, p_pos, theme, remote)

        if not self._observing:
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
            if not self._observing:
                self._draw_avatar_overlay(surface, avatar, visual_rect, self.hero.body_image)

        self._draw_border_panels(surface)

        if self._observing:
            self._draw_spectator_controls(surface)

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
        return remote.body_frames_by_state[remote.animation.state][remote.animation.frame_index]

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

    def _spectator_control_rects(self) -> tuple[pygame.Rect, pygame.Rect]:
        center_x = INTERNAL_WIDTH // 2
        y = INTERNAL_HEIGHT - 28
        prev_rect = pygame.Rect(center_x - 64, y, 18, 14)
        next_rect = pygame.Rect(center_x + 46, y, 18, 14)
        return prev_rect, next_rect

    def _scale_window_rect(self, rect: pygame.Rect) -> pygame.Rect:
        display = self.context.display_manager
        scale = display.config.selected_scale if display is not None else 1
        return pygame.Rect(rect.x * scale, rect.y * scale, rect.w * scale, rect.h * scale)

    def _draw_spectator_controls(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        prev_rect, next_rect = self._spectator_control_rects()
        panel_rect = pygame.Rect(prev_rect.right + 4, prev_rect.y, next_rect.left - prev_rect.right - 8, prev_rect.h)
        prev_window = self._scale_window_rect(prev_rect)
        next_window = self._scale_window_rect(next_rect)
        panel_window = self._scale_window_rect(panel_rect)

        alive_ids = self._alive_spectator_ids()
        target_id = self._spectate_player_id if self._spectate_player_id in alive_ids else None
        if target_id is None and alive_ids:
            target_id = self._default_spectator_target()
            self._set_spectator_target(target_id, snap=True)
        name = self._name_by_id.get(target_id, f"P{target_id}") if target_id is not None else "No live targets"
        label = self._fit_text(f"Watching {name}", self.context.small_font, max(24, panel_window.w - 12))

        card = pygame.Surface(panel_window.size, pygame.SRCALPHA)
        card.fill((*theme.bg_panel, 220))
        surface.blit(card, panel_window.topleft)
        pygame.draw.rect(surface, theme.border, panel_window, width=1, border_radius=6)
        text = self.context.small_font.render(label, True, theme.text_warn)
        surface.blit(text, text.get_rect(center=panel_window.center))

        enabled = len(alive_ids) > 1
        mouse_pos = self.context.mouse_pos
        ui.draw_button(
            surface,
            self.context.small_font,
            ui.Button(prev_window, "<", enabled),
            theme,
            hovered=enabled and prev_rect.collidepoint(mouse_pos),
            variant="neutral",
        )
        ui.draw_button(
            surface,
            self.context.small_font,
            ui.Button(next_window, ">", enabled),
            theme,
            hovered=enabled and next_rect.collidepoint(mouse_pos),
            variant="neutral",
        )

    def _player_position(self, player_id: int) -> tuple[float, float] | None:
        my_id = self.context.network.id if self.context.network else -1
        if player_id == my_id and self.hero is not None and not self._observing:
            return (self.hero.pos.x, self.hero.pos.y)
        return self._remote_positions.get(player_id)

    def _standings_rows(self) -> list[tuple[str, str]]:
        ids = {pid for pid, _ready, _name in self.context.roster}
        ids.update(self._name_by_id.keys())
        ids.update(self._placements_by_id.keys())

        live_rows = []
        placed_rows = []
        for player_id in ids:
            name = self._name_by_id.get(player_id, f"P{player_id}")
            placement = self._placements_by_id.get(player_id)
            position = self._player_position(player_id)
            if placement is None and position is not None:
                live_rows.append((position[1], player_id, name))
            elif placement is not None:
                placed_rows.append((placement, player_id, name))

        rows: list[tuple[str, str]] = []
        for rank, (_y, _pid, name) in enumerate(sorted(live_rows), start=1):
            rows.append((f"{rank}. {name}", "LIVE"))
        for placement, _pid, name in sorted(placed_rows):
            rows.append((f"{placement}. {name}", "OUT"))
        return rows

    def _platform_gap_info(self) -> tuple[int | None, int | None]:
        focus = self._observer_focus_position() if self._observing else None
        if focus is None and self.hero is not None:
            focus = (self.hero.pos.x, self.hero.pos.y)
        if focus is None or not self.platforms:
            return None, None
        focus_y = focus[1]
        centers = sorted(float(platform.rect.centery) for platform in self.platforms)
        above = [y for y in centers if y < focus_y]
        below = [y for y in centers if y >= focus_y]
        next_above = max(above) if above else None
        current_or_below = min(below) if below else None
        if next_above is None:
            return None, None
        next_distance = max(0, int(round(focus_y - next_above)))
        if current_or_below is None:
            upper = [y for y in centers if y < next_above]
            platform_gap = int(round(next_above - max(upper))) if upper else None
        else:
            platform_gap = int(round(current_or_below - next_above))
        return platform_gap, next_distance

    def _fit_text(self, text: str, font: pygame.font.Font, max_width: int) -> str:
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = "."
        out = text
        while out and font.size(out + ellipsis)[0] > max_width:
            out = out[:-1]
        return (out + ellipsis) if out else ellipsis

    def _draw_panel_text(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        pos: tuple[int, int],
        color: tuple[int, int, int],
        max_width: int,
    ) -> int:
        label = self._fit_text(text, font, max_width)
        surface.blit(font.render(label, True, color), pos)
        return font.get_height() + 4

    def _draw_border_panels(self, surface: pygame.Surface):
        display = self.context.display_manager
        if display is None:
            return
        theme = DEFAULT_THEME
        scale = display.config.selected_scale
        panel_w = BORDER_WIDTH * scale
        if panel_w <= 0:
            return

        left = pygame.Rect(0, 0, panel_w, surface.get_height())
        right = pygame.Rect(PLAYABLE_RIGHT * scale, 0, panel_w, surface.get_height())
        for rect in (left, right):
            shade = pygame.Surface(rect.size, pygame.SRCALPHA)
            shade.fill((8, 10, 18, 105))
            surface.blit(shade, rect.topleft)

        pad = 8
        y = pad
        max_text_w = max(24, left.w - (pad * 2))
        y += self._draw_panel_text(surface, self.context.tiny_font, "STANDINGS", (left.x + pad, y), theme.text_warn, max_text_w)
        for name, status in self._standings_rows()[:6]:
            y += self._draw_panel_text(surface, self.context.tiny_font, name, (left.x + pad, y), theme.text, max_text_w)
            y += self._draw_panel_text(surface, self.context.tiny_font, status, (left.x + pad, y), theme.text_muted, max_text_w)

        avatar = self.context.avatar_window_surface
        y = pad
        max_text_w = max(24, right.w - (pad * 2))
        y += self._draw_panel_text(surface, self.context.tiny_font, "AVATAR", (right.x + pad, y), theme.text_warn, max_text_w)
        if avatar is not None:
            avatar_size = min(right.w - (pad * 2), 54)
            target = pygame.Rect(right.x + (right.w - avatar_size) // 2, y, avatar_size, avatar_size)
            scaled_avatar = pygame.transform.smoothscale(avatar, target.size)
            surface.blit(scaled_avatar, target)
            pygame.draw.rect(surface, theme.border_focus, target, width=1, border_radius=4)
            y = target.bottom + 10
        else:
            y += self._draw_panel_text(surface, self.context.tiny_font, "Default", (right.x + pad, y), theme.text_muted, max_text_w)

        gap, next_distance = self._platform_gap_info()
        y += self._draw_panel_text(surface, self.context.tiny_font, "PLATFORMS", (right.x + pad, y), theme.text_warn, max_text_w)
        if gap is not None:
            y += self._draw_panel_text(surface, self.context.tiny_font, f"Gap {gap}px", (right.x + pad, y), theme.text, max_text_w)
        if next_distance is not None:
            self._draw_panel_text(surface, self.context.tiny_font, f"Next {next_distance}px", (right.x + pad, y), theme.text_muted, max_text_w)

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
