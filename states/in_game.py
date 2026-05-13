import logging
from dataclasses import dataclass
import math
import random
import time
import zlib

import pygame

from app.fonts import load_ui_font
from app.input_config import CONTROL_SCHEME_ARROWS, normalize_control_scheme
from network import network_handler as nw
from network import protocol
from network.orb_effect_sync import (
    ORB_EFFECT_UNSPECIFIED,
    apply_effect_id_to_hud_timers,
    effect_id_from_collect_result,
    is_valid_effect_id,
    tick_hud_timers,
)
from player_scripts.animation import AnimationState, load_spritesheet_frames
from player_scripts.avatar_sprite import AVATAR_RECT, compose_player_frames, make_default_avatar
from player_scripts import player as pl
from states.common import ScreenState
from ui.gameplay_effects_hud import draw_playable_effect_acquire_toasts
from ui.ingame_layout import InGameLayoutRenderer, InGameNotification, RankingRow
from ui.pixel_chrome import DEFAULT_PIXEL_STYLE, draw_neutral_button, draw_panel_shell, draw_well, line_width_for_scale
from ui.theme import DEFAULT_THEME
from world.assets import load_world_assets
from world.constants import (
    BORDER_WIDTH,
    INTERNAL_HEIGHT,
    INTERNAL_WIDTH,
    PLAYABLE_RIGHT,
    PLAYABLE_WIDTH,
    PLAYABLE_X,
    PLAYER_FRAME_HEIGHT,
    PLAYER_FRAME_WIDTH,
    PLAYER_HITBOX_HEIGHT,
    PLAYER_HITBOX_WIDTH,
)
from world.level_system import create_level_platforms, generate_level, level_preview_seed
from world.rendering import LevelRenderer
from world.shapes.goal import Goal
from world.shapes.powerup import PowerUp, create_orb_powerups_from_platform_specs
from player_scripts import camera

LOGGER = logging.getLogger(__name__)

_ORB_EFFECT_READABLE = {
    "speed": "Speed Buff",
    "jump": "Jump Buff",
    "shield": "Shield Buff",
    "double_jump": "Double Jump Buff",
    "launch": "Launch Boost",
    "reverse_control": "Reverse Control",
    "slippery": "Slippery",
    "slow_falling": "Slow Falling",
    "heavy": "Heavy",
    "weak_jump": "Weak Jump",
    "shield_blocked": "Shield Destroyed",
}
_ORB_DEBUFF_EFFECTS = frozenset({"reverse_control", "slippery", "slow_falling", "heavy", "weak_jump"})

AVATAR_FALLBACK_DELAY_SEC = 1.0

_SPECTATOR_BAR_Y = INTERNAL_HEIGHT - 32
_SPECTATOR_BTN_W, _SPECTATOR_BTN_H = 22, 15
_SPECTATOR_PANEL_W = 128
_SPECTATOR_GAP = 5
_SPECTATOR_OUTER_MARGIN = 4


@dataclass
class RemotePlayer:
    position: tuple[float, float]
    animation: AnimationState
    body_frames_by_state: dict[str, list[pygame.Surface]]


class InGameState(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

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
        self._avatar_payload: bytes | None = None
        self._avatar_id = 0
        self._avatar_fallback_elapsed = 0.0
        self._avatar_fallback_sent = False
        self._paused_players: dict[int, float] = {}
        self._pause_heartbeat_elapsed = 0.0
        self._observing = False
        self._finish_pending = False
        self._death_pending = False
        self._active_match_id = 0
        self._spectate_player_id: int | None = None
        self._spectate_snap_pending = False
        self._placements_by_id: dict[int, int] = {}
        self.goal: Goal | None = None
        self._goal_reached = False
        self.powerups: list = []
        self._window_hud_font: pygame.font.Font | None = None
        self._platform_send_elapsed = 0.0
        self._last_platforms_sent = -1
        self._platforms_reached_by_id: dict[int, int] = {}
        self._finished_player_ids: set[int] = set()
        self._notification_queue: list[InGameNotification] = []
        self._active_notification: InGameNotification | None = None
        self._notification_elapsed = 0.0
        self._ui_elapsed = 0.0
        self._ingame_layout: InGameLayoutRenderer | None = None
        self._status_notice_cooldown = 0.0
        self._effect_acquire_toasts: list[tuple[str, bool, float]] = []
        self._remote_orb_hud_timers: dict[int, dict[str, float]] = {}

    def enter(self):
        self.camera = camera.Camera(INTERNAL_WIDTH, INTERNAL_HEIGHT)
        self._dead_sent = False
        self._elimination_feed = []
        self._remote_positions = {}
        self._remote_players = {}
        self._remote_model_frames_cache = {}
        self._name_by_id = {pid: name for pid, _r, name in self.context.roster}
        self.world_assets = load_world_assets(self.context.project_root)
        self.level_renderer = LevelRenderer(self.world_assets)
        selected_level = protocol.normalize_level_id(getattr(self.context, "selected_level", protocol.DEFAULT_LEVEL_ID))
        level_seed = int(getattr(self.context, "level_seed", 0) or 0) & protocol.UINT32_MAX
        if level_seed == 0:
            level_seed = level_preview_seed(selected_level)
        level = generate_level(selected_level, level_seed)
        self.current_level = level.level_id
        self.platforms = create_level_platforms(level, self.world_assets.platform_normal)
        self.powerups = create_orb_powerups_from_platform_specs(level.platforms, rng_seed=level.seed)
        LOGGER.info(
            "Loaded level=%s seed=%s platforms=%s goal=(%s,%s)",
            level.level_id,
            level.seed,
            len(level.platforms),
            level.goal_center_x,
            level.goal_y,
        )
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
        self._avatar_payload = None
        self._avatar_id = 0
        self._avatar_fallback_elapsed = 0.0
        self._avatar_fallback_sent = False
        self._paused_players = {}
        self._pause_heartbeat_elapsed = 0.0
        self._observing = False
        self._finish_pending = False
        self._death_pending = False
        self._active_match_id = max(self.context.current_match_id, self.context.network.current_match_id if self.context.network else 0)
        self._spectate_player_id = None
        self._spectate_snap_pending = False
        self._placements_by_id = {}
        self._platforms_reached_by_id = {}
        self._finished_player_ids = set()
        self._notification_queue = []
        self._active_notification = None
        self._notification_elapsed = 0.0
        self._ui_elapsed = 0.0
        self._status_notice_cooldown = 0.0
        self._effect_acquire_toasts = []
        self._remote_orb_hud_timers.clear()
        self.goal = Goal(level.goal_center_x, level.goal_y, width=level.goal_width)
        self._goal_reached = False
        self._window_hud_font = None
        self._ingame_layout = InGameLayoutRenderer(self.context.project_root)
        self._platform_send_elapsed = 0.0
        self._last_platforms_sent = -1
        self._seed_remote_players_from_roster(base_start)
        self._send_initial_player_state()
        if not self.context.local_player_alive:
            self._observing = True
            self._dead_sent = True
            if self.context.network is not None:
                self.context.network.set_client_state(protocol.CLIENT_STATE_SPECTATING)
            self._set_spectator_target(self._default_spectator_target(), snap=True)

    def _spectator_strafe_keys(self) -> tuple[int, int]:
        if normalize_control_scheme(self.context.control_scheme) == CONTROL_SCHEME_ARROWS:
            return pygame.K_LEFT, pygame.K_RIGHT
        return pygame.K_a, pygame.K_d

    def handle_event(self, event):
        super().handle_event(event)
        if not self._observing or self._paused_players:
            return
        if event.type == pygame.KEYDOWN:
            left_k, right_k = self._spectator_strafe_keys()
            if event.key == right_k:
                self._cycle_spectator_target(1)
                return
            if event.key == left_k:
                self._cycle_spectator_target(-1)
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            _outer, prev_rect, _panel, next_rect = self._spectator_controls_layout_logical()
            prev_win = self._scale_window_rect(prev_rect)
            next_win = self._scale_window_rect(next_rect)
            if prev_win.collidepoint(event.pos):
                self._cycle_spectator_target(-1)
                return
            if next_win.collidepoint(event.pos):
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
        return self.context.avatar_receiver.get_model(player_id) or (
            protocol.DEFAULT_MODEL_TYPE,
            protocol.DEFAULT_MODEL_COLOR,
        )

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

    def _sync_orb_pickup(self, orb_index: int, cooldown_sec: int) -> None:
        if not (0 <= orb_index < len(self.powerups)):
            return
        powerup = self.powerups[orb_index]
        if powerup.active:
            powerup.start_cooldown(float(cooldown_sec))

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
            elif isinstance(event, (nw.AvatarHeaderEvent, nw.AvatarChunkEvent)):
                my_id = self.context.network.id if self.context.network else -1
                receiver = self.context.avatar_receiver
                old_model = receiver.get_model(event.player_id)
                receiver.handle_event(event, my_id)
                if isinstance(event, nw.AvatarHeaderEvent) and receiver.get_model(event.player_id) != old_model:
                    self._rebuild_remote_player_model(event.player_id)
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
            elif isinstance(event, nw.OrbCollectEvent):
                self._sync_orb_pickup(event.orb_index, event.cooldown_sec)
                my_id = self.context.network.id if self.context.network else -1
                if (
                    event.player_id != my_id
                    and is_valid_effect_id(event.effect_id)
                    and int(event.effect_id) != ORB_EFFECT_UNSPECIFIED
                ):
                    remote = self._remote_orb_hud_timers.setdefault(event.player_id, {})
                    apply_effect_id_to_hud_timers(event.effect_id, remote)
            elif isinstance(event, nw.GoalEvent):
                self._finished_player_ids.add(event.player_id)
                if event.player_id == (self.context.network.id if self.context.network else -1):
                    self._finish_pending = False
            elif isinstance(event, nw.PlatformProgressEvent):
                self._platforms_reached_by_id[event.player_id] = max(
                    self._platforms_reached_by_id.get(event.player_id, 0),
                    int(event.platforms_reached),
                )
            elif isinstance(event, nw.EliminationEvent):
                name = self._name_by_id.get(event.player_id, f"id {event.player_id}")
                LOGGER.info("Elimination received player_id=%s name=%s placement=%s", event.player_id, name, event.placement)
                my_id = self.context.network.id if self.context.network else -1
                finished_goal = event.player_id in self._finished_player_ids or (event.player_id == my_id and self._goal_reached)
                if finished_goal:
                    feed_line = f"{name} finished — place {event.placement}"
                    self._finished_player_ids.add(event.player_id)
                    self._enqueue_ingame_notification("finished", name, event.placement)
                else:
                    feed_line = f"{name} eliminated — place {event.placement}"
                    self._enqueue_ingame_notification("eliminated", name, event.placement)
                self._elimination_feed.append(feed_line)
                self._placements_by_id[event.player_id] = event.placement
                self._remote_orb_hud_timers.pop(event.player_id, None)
                if event.player_id == my_id:
                    self._finish_pending = False
                    self._death_pending = False
                    self.context.local_player_alive = False
                    self._observing = True
                    self._dead_sent = True
                    if self.context.network is not None:
                        self.context.network.set_client_state(protocol.CLIENT_STATE_SPECTATING)
                    self._set_spectator_target(self._default_spectator_target(), snap=True)
                    if finished_goal:
                        LOGGER.info("Local player finish confirmed; spectating player_id=%s", event.player_id)
                        self._set_finish_spectator_status_message()
                    else:
                        LOGGER.info("Local player eliminated; switched to observing player_id=%s", event.player_id)
                        self.context.set_status("Eliminated. Observing the remaining players.", duration=3.0)
                else:
                    self._remote_players.pop(event.player_id, None)
                    self._remote_positions.pop(event.player_id, None)
                    # Keep avatar in receiver — results screen reads it from the same dict.
                    if self._spectate_player_id == event.player_id:
                        self._set_spectator_target(self._default_spectator_target(), snap=True)
                self._paused_players.pop(event.player_id, None)
            elif isinstance(event, nw.ReconnectSnapshotEvent):
                self._remote_orb_hud_timers.clear()
                self.context.room_name = event.room_name
                self.context.selected_level = protocol.normalize_level_id(event.selected_level)
                self.context.level_seed = int(event.level_seed) & protocol.UINT32_MAX
                wall = int(event.match_start_unix_sec) & protocol.UINT32_MAX
                self.context.match_start_unix_sec = wall if wall != 0 else int(time.time())
                self.context.current_match_id = max(self.context.current_match_id, event.match_id)
                self._active_match_id = max(self._active_match_id, event.match_id)
                self.context.active_countdown_id = max(self.context.active_countdown_id, event.countdown_id)
                self.context.start_pos = (event.x, event.y)
                self.context.local_player_alive = bool(event.alive)
                if self.hero is not None:
                    self.hero.pos.x = event.x
                    self.hero.pos.y = event.y
                    self.hero.rect.center = (int(round(event.x)), int(round(event.y)))
                if event.room_state == protocol.STATE_LOBBY:
                    self.switch("host_lobby" if self.context.is_host else "joined_lobby")
                    return True
                if not event.alive:
                    self._observing = True
                    self._dead_sent = True
                    if self.context.network is not None:
                        self.context.network.set_client_state(protocol.CLIENT_STATE_SPECTATING)
                    self._set_spectator_target(self._default_spectator_target(), snap=True)
            elif isinstance(event, nw.GameEndEvent):
                if not self.accept_game_end_event(event):
                    continue
                self._finish_pending = False
                self._death_pending = False
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
                        self._remote_orb_hud_timers.pop(player_id, None)
                        self._platforms_reached_by_id.pop(player_id, None)
                        self._finished_player_ids.discard(player_id)
                        # Keep avatar in receiver — results screen reads it from the same dict.
                        if self._spectate_player_id == player_id:
                            self._set_spectator_target(self._default_spectator_target(), snap=True)
                for pid, _ready, name in event.entries:
                    self._name_by_id[pid] = name
                    my_id = self.context.network.id if self.context.network else -1
                    if pid == my_id or pid in self._placements_by_id:
                        continue
                    if pid not in self._remote_players:
                        position = self._remote_positions.get(
                            pid,
                            self._spawn_position_for_player(pid, self.context.start_pos),
                        )
                        self._remote_positions[pid] = position
                        self._get_remote_player(pid, position)
        return False

    def update(self, dt: float):
        net = self.context.network
        if net is None or self.hero is None:
            return
        self._ui_elapsed += dt
        self._status_notice_cooldown = max(0.0, self._status_notice_cooldown - dt)
        self._tick_ingame_notifications(dt)
        self._prune_effect_acquire_toasts()
        self._tick_remote_orb_hud_timers(dt)

        if self._drain_network():
            return
        if self.machine.current_state is not self or self.context.network is not net or not net.is_open:
            return
        if self._reconcile_heartbeat_authority(net):
            return

        self._send_avatar_fallback_if_needed(dt, net)

        for powerup in self.powerups:
            powerup.update(dt)

        if self._paused_players:
            self._tick_pause(dt, net)
            return

        if self._observing:
            self._tick_observer(dt)
            return

        if self._finish_pending or self._death_pending:
            for remote in self._remote_players.values():
                remote.animation.update(dt)
            if self.goal is not None:
                self.goal.update(dt)
            if self.hero and self.camera:
                self.camera.update(self.hero)
            return

        self.hero.update(dt, INTERNAL_WIDTH, INTERNAL_HEIGHT, self.platforms, self.context.control_scheme)

        pr = self.hero.platforms_reached_count()
        my_id = self.context.network.id if self.context.network else -1
        if my_id >= 0:
            self._platforms_reached_by_id[my_id] = max(self._platforms_reached_by_id.get(my_id, 0), pr)
        if pr != self._last_platforms_sent:
            self._platform_send_elapsed += dt
            if self._platform_send_elapsed >= 0.12:
                net.send_platform_progress(pr)
                self._last_platforms_sent = pr
                self._platform_send_elapsed = 0.0
        else:
            self._platform_send_elapsed = 0.0

        # Check powerup collisions
        for i, powerup in enumerate(self.powerups):
            if powerup.active and self.hero.rect.colliderect(powerup.rect):
                cooldown_sec = random.randint(protocol.ORB_COOLDOWN_MIN_SEC, protocol.ORB_COOLDOWN_MAX_SEC)
                powerup.start_cooldown(float(cooldown_sec))
                actual_effect = self.hero.collect_power_up(powerup.effect_type)
                eid = effect_id_from_collect_result(actual_effect)
                net.send_orb_collect(i, cooldown_sec, eid)
                readable = _ORB_EFFECT_READABLE.get(actual_effect, "Unknown")
                self.context.set_status(f"Orb: {readable}", duration=3.0)
                self._push_effect_acquire_toast_from_orb(actual_effect, readable)

        for remote in self._remote_players.values():
            remote.animation.update(dt)

        if self.goal is not None:
            self.goal.update(dt)

        if self.hero and self.camera:
            self.camera.update(self.hero)

        if not self._dead_sent and self.camera.has_fallen_below(self.hero):
            self._dead_sent = True
            self._death_pending = True
            self.context.local_player_alive = False
            LOGGER.info("Local player fell below camera; sending DEAD (pending server confirmation)")
            net.send_dead()
            self.context.set_status("Death pending server confirmation...", duration=2.0)

        if (
            not self._goal_reached
            and not self._dead_sent
            and not self._finish_pending
            and self.goal is not None
            and self.hero.rect.colliderect(self.goal.rect)
        ):
            self._goal_reached = True
            self._finish_pending = True
            self.context.local_player_alive = False
            LOGGER.info("Local player reached goal; sending GOAL (pending server confirmation)")
            net.send_goal()
            self.context.set_status("Finish pending server confirmation...", duration=2.0)

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

    def _tick_remote_orb_hud_timers(self, dt: float) -> None:
        for timers in list(self._remote_orb_hud_timers.values()):
            tick_hud_timers(dt, timers)
        ids = list(self._remote_orb_hud_timers.keys())
        for pid in ids:
            if not self._remote_orb_hud_timers.get(pid):
                self._remote_orb_hud_timers.pop(pid, None)

    def _hud_powerup_timers_overlay(self) -> dict[str, float]:
        """Left-panel buff icons: spectating follows the targeted live player's synced HUD timers."""
        if self._observing:
            alive = self._alive_spectator_ids()
            tid = self._spectate_player_id
            if tid is None or tid not in alive:
                return {}
            return dict(self._remote_orb_hud_timers.get(tid, {}))
        if self.hero is None:
            return {}
        return self.hero.active_power_up_timers()

    def _prune_effect_acquire_toasts(self) -> None:
        now = time.monotonic()
        self._effect_acquire_toasts = [(t, d, e) for t, d, e in self._effect_acquire_toasts if e > now]

    def _push_effect_acquire_toast_from_orb(self, actual_effect: str, readable: str) -> None:
        if actual_effect == "shield_blocked":
            msg, is_debuff = "Shield destroyed", True
        else:
            base = readable if readable != "Unknown" else "Effect"
            msg = f"{base} acquired"
            is_debuff = actual_effect in _ORB_DEBUFF_EFFECTS
        expire = time.monotonic() + 2.35
        self._effect_acquire_toasts.append((msg, is_debuff, expire))
        if len(self._effect_acquire_toasts) > 5:
            self._effect_acquire_toasts = self._effect_acquire_toasts[-5:]

    def _notify_status_once(self, message: str, duration: float = 2.0, cooldown: float = 1.5) -> None:
        if self._status_notice_cooldown > 0.0:
            return
        self._status_notice_cooldown = cooldown
        self.context.set_status(message, duration=duration)

    def _reconcile_heartbeat_authority(self, net: nw.Network) -> bool:
        now = time.monotonic()
        last_ack = float(getattr(self.context, "last_heartbeat_ack_monotonic", 0.0) or 0.0)
        if last_ack <= 0.0:
            return False
        if last_ack > 0.0 and (now - last_ack) >= max(3.0, protocol.HEARTBEAT_INTERVAL_SECONDS * 3.5):
            self._notify_status_once("Reconnecting to server...", duration=2.0)
            return True

        server_state = int(getattr(self.context, "last_server_state", protocol.STATE_IN_GAME))
        if server_state == protocol.STATE_PAUSED and not self._paused_players:
            self._notify_status_once("Server paused the match. Waiting for reconnect...", duration=2.2)
            return True

        if server_state == protocol.STATE_LOBBY:
            if self.context.results_standings:
                self.switch("results")
            else:
                self._notify_status_once("Match ended on server. Returning to lobby...", duration=2.5, cooldown=2.5)
                self.switch("host_lobby" if self.context.is_host else "joined_lobby")
            return True

        server_match_id = max(self.context.current_match_id, net.current_match_id)
        if self._active_match_id != 0 and server_match_id > self._active_match_id:
            self._notify_status_once("Server advanced to a newer match. Waiting for resync...", duration=2.5)
            return True
        return False

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
            server_state = int(getattr(self.context, "last_server_state", protocol.STATE_IN_GAME))
            if server_state == protocol.STATE_PAUSED:
                self._notify_status_once("Waiting for reconnecting players...", duration=2.0)
            elif server_state == protocol.STATE_IN_GAME:
                self._notify_status_once("Waiting for server result...", duration=2.0)
            else:
                self._notify_status_once("Waiting for authoritative match state...", duration=2.0)
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

    def _set_finish_spectator_status_message(self) -> None:
        """Server echoes the same elimination packet for goal finishes — use finish wording, not 'Eliminated'."""
        if self._alive_spectator_ids():
            self.context.set_status("Finished! Watching the remaining players.", duration=3.5)
        else:
            self.context.set_status("Finished!", duration=2.5)

    def _enqueue_ingame_notification(self, kind: str, name: str, placement: int) -> None:
        if kind not in ("finished", "eliminated"):
            return
        self._notification_queue.append(
            InGameNotification(kind=kind, name=name, placement=int(placement))
        )

    def _tick_ingame_notifications(self, dt: float) -> None:
        if self._active_notification is None and self._notification_queue:
            self._active_notification = self._notification_queue.pop(0)
            self._notification_elapsed = 0.0
        if self._active_notification is None:
            return
        self._notification_elapsed += dt
        if self._notification_elapsed >= 2.5:
            self._active_notification = None
            self._notification_elapsed = 0.0

    def _avatar_for_player(self, player_id: int | None) -> pygame.Surface | None:
        if player_id is None:
            return None
        my_id = self.context.network.id if self.context.network else -1
        if player_id == my_id:
            return self.context.avatar_window_surface
        return self.context.remote_avatar_surfaces.get(player_id)

    def _estimated_platforms_for_position(self, position: tuple[float, float] | None) -> int:
        if position is None:
            return 0
        y = float(position[1])
        return sum(1 for platform in self.platforms if platform.rect.centery >= y)

    def _platform_count_for_player(self, player_id: int, position: tuple[float, float] | None) -> int:
        my_id = self.context.network.id if self.context.network else -1
        if player_id == my_id and self.hero is not None:
            position = (self.hero.pos.x, self.hero.pos.y)
        current = self._estimated_platforms_for_position(position)
        if current > 0:
            return current
        return int(self._platforms_reached_by_id.get(player_id, 0))

    def _format_platform_distance(self, local_platforms: int, other_platforms: int) -> str:
        diff = int(local_platforms) - int(other_platforms)
        if diff > 0:
            return f"+{diff} Platforms"
        if diff < 0:
            return f"{diff} Platforms"
        return "0 Platforms"

    def _ranking_rows(self) -> list[RankingRow]:
        my_id = self.context.network.id if self.context.network else -1
        ids = {pid for pid, _ready, _name in self.context.roster}
        ids.update(self._name_by_id.keys())
        ids.update(self._placements_by_id.keys())
        if my_id >= 0:
            ids.add(my_id)

        local_position = (self.hero.pos.x, self.hero.pos.y) if self.hero is not None else None
        local_platforms = self._platform_count_for_player(my_id, local_position) if my_id >= 0 else 0

        placed_slots: list[RankingRow | None] = [None] * 5
        live_candidates: list[tuple[int, float, int, str, int, pygame.Surface | None]] = []

        for player_id in sorted(ids):
            name = self._name_by_id.get(player_id, self.context.player_name if player_id == my_id else f"P{player_id}")
            position = self._player_position(player_id)
            platforms = self._platform_count_for_player(player_id, position)
            placement = self._placements_by_id.get(player_id)
            avatar = self._avatar_for_player(player_id)
            if placement is not None:
                status = "finished" if player_id in self._finished_player_ids else "eliminated"
                distance_text = "FINISHED" if status == "finished" else ""
                slot = int(placement) - 1
                if 0 <= slot < len(placed_slots):
                    placed_slots[slot] = RankingRow(
                        player_id=player_id,
                        rank=slot + 1,
                        name=name,
                        status=status,
                        platforms_reached=platforms,
                        distance_text=distance_text,
                        avatar=avatar,
                    )
                continue
            if position is not None:
                y = float(position[1])
                live_candidates.append((platforms, y, player_id, name, platforms, avatar))

        live_candidates.sort(key=lambda row: (-row[0], row[1], row[3].lower()))
        rows: list[RankingRow] = []
        live_index = 0
        for slot in range(5):
            placed = placed_slots[slot]
            if placed is not None:
                rows.append(placed)
                continue
            if live_index < len(live_candidates):
                _sort_platforms, _y, player_id, name, platforms, avatar = live_candidates[live_index]
                live_index += 1
                rows.append(
                    RankingRow(
                        player_id=player_id,
                        rank=slot + 1,
                        name=name,
                        status="live",
                        platforms_reached=platforms,
                        distance_text="YOU" if player_id == my_id else self._format_platform_distance(local_platforms, platforms),
                        avatar=avatar,
                    )
                )
                continue
            rows.append(
                RankingRow(
                    player_id=None,
                    rank=slot + 1,
                    name="Open Slot",
                    status="open",
                    platforms_reached=0,
                    distance_text="",
                    avatar=None,
                )
            )
        return rows

    def _ingame_window_hud_font(self) -> pygame.font.Font:
        if self._window_hud_font is None:
            self._window_hud_font = load_ui_font(self.context.project_root, 16, bold=True)
        return self._window_hud_font

    def _tick_pause(self, dt: float, net: nw.Network):
        for player_id in list(self._paused_players.keys()):
            self._paused_players[player_id] = max(0.0, self._paused_players[player_id] - dt)
        if self.hero is None:
            return
        self._pause_heartbeat_elapsed += dt
        if self._pause_heartbeat_elapsed >= 0.5:
            net.update_player_state(self.hero.pos.x, self.hero.pos.y, self.hero.animation.state)
            self._pause_heartbeat_elapsed = 0.0

    def _ensure_avatar_payload(self) -> bool:
        if self._avatar_payload is not None:
            return True
        self._avatar_payload = self._make_avatar_payload()
        self._avatar_id = zlib.adler32(self._avatar_payload) & 0xFFFF if self._avatar_payload else 0
        return self._avatar_payload is not None

    def _missing_remote_avatar_ids(self, local_player_id: int) -> list[int]:
        return [
            player_id
            for player_id, _ready, _name in self.context.roster
            if player_id != local_player_id and player_id not in self.context.remote_avatar_surfaces
        ]

    def _send_avatar_fallback_if_needed(self, dt: float, net: nw.Network):
        if self._avatar_fallback_sent:
            return
        self._avatar_fallback_elapsed += dt
        if self._avatar_fallback_elapsed < AVATAR_FALLBACK_DELAY_SEC:
            return
        missing_ids = self._missing_remote_avatar_ids(net.id)
        if not missing_ids:
            self._avatar_fallback_sent = True
            return
        if not self._ensure_avatar_payload():
            return
        LOGGER.info("Fallback avatar send; missing remote avatars=%s", missing_ids)
        net.send_avatar(self._avatar_id, self._avatar_payload, self.context.model_type, self.context.model_color)
        self._avatar_fallback_sent = True

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

        for powerup in self.powerups:
            if powerup.active:
                powerup.draw(surface, camera, self.world_assets.orb_frames if self.world_assets is not None else None)

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

        self.context.draw_global_messages(surface)
        scale = display.config.selected_scale
        match_elapsed = None
        if self.context.match_start_unix_sec is not None:
            match_elapsed = max(0.0, time.time() - float(self.context.match_start_unix_sec))
        my_id = self.context.network.id if self.context.network else -1
        pr_local = self._platform_count_for_player(
            my_id,
            (self.hero.pos.x, self.hero.pos.y),
        ) if my_id >= 0 else self.hero.platforms_reached_count()

        for player_id, position in self._remote_positions.items():
            if int(player_id) == my_id:
                continue
            avatar = self.context.remote_avatar_surfaces.get(player_id)
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

        if self._ingame_layout is not None:
            self._ingame_layout.draw(
                surface,
                scale,
                self._ranking_rows(),
                match_elapsed,
                self.context.room_name,
                pr_local,
                self._hud_powerup_timers_overlay(),
                self._active_notification,
                self._ui_elapsed,
            )

        if not self._observing:
            draw_playable_effect_acquire_toasts(
                surface,
                self.context.small_font,
                scale,
                [(t, d) for t, d, _ in self._effect_acquire_toasts],
                self.context.show_performance_metrics,
                self.context.tiny_font,
            )

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

    def _spectator_controls_layout_logical(self) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect]:
        """Spectator bar centered in the playable column: outer shell, <, name well, >."""
        bw, bh = _SPECTATOR_BTN_W, _SPECTATOR_BTN_H
        pw = _SPECTATOR_PANEL_W
        gap = _SPECTATOR_GAP
        m = _SPECTATOR_OUTER_MARGIN
        inner_w = bw + gap + pw + gap + bw
        cx = PLAYABLE_X + PLAYABLE_WIDTH // 2
        left = cx - inner_w // 2
        y = _SPECTATOR_BAR_Y
        prev_r = pygame.Rect(left, y, bw, bh)
        panel_r = pygame.Rect(prev_r.right + gap, y, pw, bh)
        next_r = pygame.Rect(panel_r.right + gap, y, bw, bh)
        outer = pygame.Rect(left - m, y - m, inner_w + m * 2, bh + m * 2)
        return outer, prev_r, panel_r, next_r

    def _scale_window_rect(self, rect: pygame.Rect) -> pygame.Rect:
        display = self.context.display_manager
        scale = display.config.selected_scale if display is not None else 1
        return pygame.Rect(rect.x * scale, rect.y * scale, rect.w * scale, rect.h * scale)

    def _draw_spectator_controls(self, surface: pygame.Surface):
        display = self.context.display_manager
        if display is None:
            return
        px = DEFAULT_PIXEL_STYLE
        scale_v = display.config.selected_scale
        lw = line_width_for_scale(scale_v)

        outer_l, prev_l, panel_l, next_l = self._spectator_controls_layout_logical()
        outer_w = self._scale_window_rect(outer_l)
        prev_w = self._scale_window_rect(prev_l)
        panel_w = self._scale_window_rect(panel_l)
        next_w = self._scale_window_rect(next_l)

        draw_panel_shell(surface, outer_w, lw, px)

        alive_ids = self._alive_spectator_ids()
        target_id = self._spectate_player_id if self._spectate_player_id in alive_ids else None
        if target_id is None and alive_ids:
            target_id = self._default_spectator_target()
            self._set_spectator_target(target_id, snap=True)
        name = self._name_by_id.get(target_id, f"P{target_id}") if target_id is not None else "No live targets"
        label_raw = f"Watching {name}"
        label = self._fit_text(label_raw, self.context.small_font, max(32, panel_w.w - scale_v * 4))

        draw_well(surface, panel_w, lw, px)

        enabled = len(alive_ids) > 1
        mp = self.context.mouse_pos

        draw_neutral_button(surface, prev_w, lw, px)
        if enabled and prev_w.collidepoint(mp):
            pygame.draw.rect(surface, px.hover_outline, prev_w.inflate(2, 2), width=1)

        draw_neutral_button(surface, next_w, lw, px)
        if enabled and next_w.collidepoint(mp):
            pygame.draw.rect(surface, px.hover_outline, next_w.inflate(2, 2), width=1)

        caret = self.context.small_font.render("<", True, px.text_btn_dim if not enabled else px.text_btn_bright)
        surface.blit(caret, caret.get_rect(center=prev_w.center))
        caret_r = self.context.small_font.render(">", True, px.text_btn_dim if not enabled else px.text_btn_bright)
        surface.blit(caret_r, caret_r.get_rect(center=next_w.center))

        text_color = px.text_muted if target_id is None else px.text_label
        text_s = self.context.small_font.render(label, True, text_color)
        surface.blit(text_s, text_s.get_rect(center=panel_w.center))

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
