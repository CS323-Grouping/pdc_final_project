from dataclasses import dataclass
import logging
from pathlib import Path
import queue
import secrets
import string
import subprocess
from typing import Dict, Optional, Type

import pygame

from app.display import DisplayConfig, DisplayManager
from app.message_hud import MessageHud
from app.paths import get_resource_root
from app.profile_store import ProfileSession
from app.server_process import LocalServerLauncher
from network import network_handler as nw
from network import protocol
from network.avatar_receiver import AvatarReceiver
from network.discovery import PresenceBroadcaster
from player_scripts.avatar_sprite import prepare_avatar
from player_scripts.model_assets import animation_path, load_default_head_texture
from ui.theme import DEFAULT_THEME
from world.constants import BORDER_WIDTH

from states.avatar_setup import AvatarSetupState
from states.browse_lobby import BrowseLobbyState
from states.host_lobby import HostLobbyState
from states.in_game import InGameState
from states.joined_lobby import JoinedLobbyState
from states.menu import MainMenuState
from states.results import ResultsState

LOGGER = logging.getLogger(__name__)
MAX_FRAME_DT = 1.0 / 30.0
RANDOM_PLAYER_NAME_CHARS = string.ascii_uppercase + string.digits


def random_player_name(length: int = protocol.PLAYER_NAME_MAX_LEN) -> str:
    length = max(protocol.PLAYER_NAME_MIN_LEN, min(protocol.PLAYER_NAME_MAX_LEN, int(length)))
    return "P" + "".join(secrets.choice(RANDOM_PLAYER_NAME_CHARS) for _ in range(length - 1))


@dataclass
class ReconnectTicket:
    addr: str
    port: int
    room_name: str
    player_id: int
    session_token: int
    player_name: str
    is_host: bool


PRESENCE_BY_STATE = {
    "menu": protocol.PRESENCE_STATUS_ONLINE,
    "avatar_setup": protocol.PRESENCE_STATUS_ONLINE,
    "browse_lobby": protocol.PRESENCE_STATUS_ONLINE,
    "host_lobby": protocol.PRESENCE_STATUS_LOBBY,
    "joined_lobby": protocol.PRESENCE_STATUS_LOBBY,
    "results": protocol.PRESENCE_STATUS_LOBBY,
    "in_game": protocol.PRESENCE_STATUS_IN_GAME,
}

NETWORK_CLIENT_STATE_BY_STATE = {
    "host_lobby": protocol.CLIENT_STATE_LOBBY,
    "joined_lobby": protocol.CLIENT_STATE_LOBBY,
    "results": protocol.CLIENT_STATE_RESULTS,
    "in_game": protocol.CLIENT_STATE_IN_GAME,
}


@dataclass
class AppContext:
    screen: pygame.Surface
    clock: pygame.time.Clock
    log_level: str
    display_manager: Optional[DisplayManager] = None
    running: bool = True
    player_name: str = ""
    room_name: str = "Room123"
    avatar_surface: Optional[pygame.Surface] = None
    avatar_window_surface: Optional[pygame.Surface] = None
    avatar_source_name: str = "Default avatar"
    use_custom_head: bool = False
    model_type: str = protocol.DEFAULT_MODEL_TYPE
    model_color: str = protocol.DEFAULT_MODEL_COLOR
    profile_session: Optional[ProfileSession] = None
    network: Optional[nw.Network] = None
    reconnect_ticket: Optional[ReconnectTicket] = None
    is_host: bool = False
    server_host: str = "127.0.0.1"
    server_port: int = 5555
    discovery_port: int = 5556
    roster: list = None
    countdown_remaining: Optional[float] = None
    start_pos: tuple = (100.0, 100.0)
    selected_level: int = protocol.DEFAULT_LEVEL_ID
    level_seed: int = 0
    results_standings: list = None
    return_state_after_results: str = "joined_lobby"
    active_countdown_id: int = 0
    last_countdown_id: int = 0
    current_match_id: int = 0
    last_results_match_id: int = 0
    match_start_unix_sec: int | None = None
    mouse_pos: tuple[int, int] = (0, 0)
    presence_instance_id: int = 0
    presence_status: int = protocol.PRESENCE_STATUS_ONLINE
    presence_broadcaster: Optional[PresenceBroadcaster] = None
    log_dir: Optional[Path] = None
    remote_avatar_surfaces: Optional[dict[int, pygame.Surface]] = None
    avatar_receiver: Optional[AvatarReceiver] = None
    server: Optional[LocalServerLauncher] = None
    messages: Optional[MessageHud] = None

    def __post_init__(self):
        if not self.player_name:
            self.player_name = random_player_name()
        if self.presence_instance_id == 0:
            self.presence_instance_id = secrets.randbits(32) or 1
        t = DEFAULT_THEME
        self.font = pygame.font.SysFont(t.font_body, t.size_large)
        self.small_font = pygame.font.SysFont(t.font_body, t.size_small)
        self.tiny_font = pygame.font.SysFont(t.font_body, t.size_tiny)
        self.title_font = pygame.font.SysFont(t.font_title, t.size_title)
        self.project_root = get_resource_root()
        if self.roster is None:
            self.roster = []
        if self.results_standings is None:
            self.results_standings = []
        if self.remote_avatar_surfaces is None:
            self.remote_avatar_surfaces = {}
        if self.avatar_receiver is None:
            self.avatar_receiver = AvatarReceiver(self.remote_avatar_surfaces)
        if self.server is None:
            self.server = LocalServerLauncher(
                project_root=self.project_root,
                log_level=self.log_level,
                log_dir_provider=lambda: self.log_dir,
                server_host=self.server_host,
                server_port=self.server_port,
                discovery_port=self.discovery_port,
            )
        if self.messages is None:
            self.messages = MessageHud(
                small_font=self.small_font,
                tiny_font=self.tiny_font,
                window_border_inset_provider=self.window_border_inset_px,
                theme=DEFAULT_THEME,
            )
        if self.avatar_surface is None or self.avatar_window_surface is None:
            self.use_default_head(save=False)

    # --- MessageHud delegation (kept on AppContext for backward-compat) -------
    def set_banner(self, message: str, duration: float = 4.0):
        self.messages.set_banner(message, duration)

    def set_status(self, message: str, duration: float = 3.0):
        self.messages.set_status(message, duration)

    @property
    def banner_message(self) -> str:
        return self.messages.banner_message if self.messages is not None else ""

    @property
    def status_message(self) -> str:
        return self.messages.status_message if self.messages is not None else ""

    @property
    def dock_global_messages_bottom(self) -> bool:
        return self.messages.dock_global_messages_bottom if self.messages is not None else False

    @dock_global_messages_bottom.setter
    def dock_global_messages_bottom(self, value: bool) -> None:
        if self.messages is not None:
            self.messages.dock_global_messages_bottom = value

    def _set_avatar_source(self, source: pygame.Surface, source_name: str, use_custom_head: bool):
        self.avatar_window_surface = source
        self.avatar_surface = prepare_avatar(source)
        self.avatar_source_name = source_name
        self.use_custom_head = use_custom_head

    def use_default_head(self, save: bool = True):
        self._set_avatar_source(load_default_head_texture(self.project_root), "Default head", False)
        if save:
            self.save_profile()

    def cache_custom_head(self, source: pygame.Surface, source_name: str):
        self._set_avatar_source(source, source_name, True)
        if self.profile_session is not None:
            self.profile_session.profile_dir.mkdir(parents=True, exist_ok=True)
            pygame.image.save(source, str(self.profile_session.custom_head_path))
        self.save_profile()

    def current_avatar_source(self) -> pygame.Surface:
        if self.avatar_window_surface is not None:
            return self.avatar_window_surface
        return load_default_head_texture(self.project_root)

    def current_avatar_frame(self) -> pygame.Surface:
        if self.avatar_surface is not None:
            return self.avatar_surface
        return prepare_avatar(self.current_avatar_source())

    def player_animation_path(self, model_type: str | None = None, model_color: str | None = None) -> Path:
        return animation_path(
            self.project_root,
            model_type or self.model_type,
            model_color or self.model_color,
        )

    def apply_profile_session(self, session: ProfileSession):
        self.profile_session = session
        self.player_name = session.data.player_name
        self.model_type = protocol.normalize_model_type(session.data.model_type)
        self.model_color = protocol.normalize_model_color(session.data.model_color)
        if session.data.use_custom_head and session.custom_head_path.exists():
            try:
                source = pygame.image.load(str(session.custom_head_path)).convert_alpha()
                self._set_avatar_source(source, session.custom_head_path.name, True)
            except pygame.error:
                self.use_default_head(save=False)
        else:
            self.use_default_head(save=False)

    def set_model_color(self, model_color: str, save: bool = True):
        self.model_color = protocol.normalize_model_color(model_color)
        if save:
            self.save_profile()

    def save_profile(self):
        if self.profile_session is None:
            return
        self.profile_session.data.player_name = self.player_name
        self.profile_session.data.model_type = protocol.normalize_model_type(self.model_type)
        self.profile_session.data.model_color = protocol.normalize_model_color(self.model_color)
        self.profile_session.data.use_custom_head = self.use_custom_head
        self.profile_session.save()

    def window_border_inset_px(self) -> int:
        """Horizontal pillar width in **window** pixels (internal border is `BORDER_WIDTH` × scale)."""
        if self.display_manager is None:
            return BORDER_WIDTH
        return BORDER_WIDTH * int(self.display_manager.config.selected_scale)

    def tick_timers(self, dt: float):
        self.messages.tick(dt)
        if self.countdown_remaining is not None:
            self.countdown_remaining = max(0.0, self.countdown_remaining - dt)

    def reserved_bottom_message_strip_px(self) -> int:
        return self.messages.reserved_bottom_strip_px()

    def draw_global_messages(self, surface: Optional[pygame.Surface] = None):
        self.messages.draw(surface or self.screen)

    def update_mouse_pos(self, use_internal: bool = False):
        pos = pygame.mouse.get_pos()
        if use_internal and self.display_manager is not None:
            self.mouse_pos = self.display_manager.window_to_internal(pos)
        else:
            self.mouse_pos = pos

    def apply_display_settings(self, selected_scale: int, fullscreen: bool):
        if self.display_manager is None:
            return False
        config = DisplayConfig(selected_scale=selected_scale, fullscreen=fullscreen)
        try:
            self.screen = self.display_manager.apply_config(config)
        except pygame.error as err:
            self.set_status(f"Could not apply display mode: {err}", duration=4.0)
            return False
        return True

    def to_render_event(self, event, use_internal: bool = False):
        if not use_internal or self.display_manager is None:
            return event
        return self.display_manager.to_render_event(event)

    # --- LocalServerLauncher delegation (kept on AppContext for backward-compat) -------
    def start_local_server(self, room_name: str) -> bool:
        ok = self.server.start(room_name)
        self.server_port = self.server.server_port
        return ok

    def stop_server(self):
        self.server.stop()

    def wait_for_server_exit(self, timeout: float = 0.75) -> bool:
        return self.server.wait_for_exit(timeout)

    @property
    def server_process(self) -> Optional[subprocess.Popen]:
        return self.server.process if self.server is not None else None

    def attach_network(self, network_obj: nw.Network, is_host: bool, room_name: str, start_pos):
        self.detach_network(send_disconnect=False)
        self.network = network_obj
        self.is_host = is_host
        self.room_name = room_name
        self.start_pos = start_pos or (100.0, 100.0)
        self.selected_level = protocol.normalize_level_id(getattr(network_obj, "selected_level", protocol.DEFAULT_LEVEL_ID))
        self.level_seed = 0
        self.roster = []
        self.countdown_remaining = None
        self.active_countdown_id = 0
        self.last_countdown_id = 0
        self.current_match_id = 0
        self.last_results_match_id = 0
        self.results_standings = []
        self.remember_reconnect_ticket()
        self.network.start_receiver()
        LOGGER.info(
            "Attached network player_id=%s host=%s room=%s addr=%s start_pos=%s",
            self.network.id,
            self.is_host,
            self.room_name,
            self.network.addr,
            self.start_pos,
        )

    def remember_reconnect_ticket(self):
        if self.network is None:
            return
        if self.network.id < 0 or self.network.session_token == 0:
            return
        addr, port = self.network.addr
        if not addr or port <= 0:
            return
        self.reconnect_ticket = ReconnectTicket(
            addr=addr,
            port=port,
            room_name=self.room_name,
            player_id=self.network.id,
            session_token=self.network.session_token,
            player_name=self.player_name,
            is_host=self.is_host,
        )

    def reset_lobby_after_game(self):
        self.countdown_remaining = None
        self.roster = [(player_id, False, name) for player_id, _ready, name in self.roster]
        self.match_start_unix_sec = None

    def detach_network(self, send_disconnect: bool = True, preserve_reconnect: bool = False):
        if self.network is None:
            self.is_host = False
            self.roster = []
            self.countdown_remaining = None
            if not preserve_reconnect:
                self.reconnect_ticket = None
            return
        try:
            if send_disconnect:
                LOGGER.info("Sending disconnect player_id=%s addr=%s", self.network.id, self.network.addr)
                self.network.disconnect()
        finally:
            LOGGER.info("Detaching network player_id=%s preserve_reconnect=%s", self.network.id, preserve_reconnect)
            self.network.close()
            self.network = None
            self.is_host = False
            self.roster = []
            self.countdown_remaining = None
            if not preserve_reconnect:
                self.reconnect_ticket = None

    def drain_network_events(self):
        if self.network is None:
            return []
        events = []
        while True:
            try:
                events.append(self.network.events.get_nowait())
            except queue.Empty:
                break
        return events

    def shutdown(self):
        LOGGER.info("App shutdown requested host=%s network=%s", self.is_host, self.network is not None)
        self.save_profile()
        self.stop_presence()
        if self.is_host and self.network is not None:
            LOGGER.info("Host shutdown: sending close room")
            self.network.close_room()
            self.wait_for_server_exit(timeout=0.75)
            self.detach_network(send_disconnect=False)
        else:
            self.detach_network(send_disconnect=True)
        self.stop_server()
        if self.profile_session is not None:
            self.profile_session.release()

    def start_presence(self):
        if self.presence_broadcaster is not None:
            return
        self.presence_broadcaster = PresenceBroadcaster(
            instance_id=self.presence_instance_id,
            player_name_provider=lambda: self.player_name,
            status_provider=lambda: self.presence_status,
            discovery_port=self.discovery_port,
        )
        self.presence_broadcaster.start()

    def stop_presence(self):
        if self.presence_broadcaster is None:
            return
        self.presence_broadcaster.stop()
        self.presence_broadcaster = None


class StateMachine:
    def __init__(self, context: AppContext):
        self.context = context
        self.current_state = None
        self.state_map: Dict[str, Type] = {
            "menu": MainMenuState,
            "avatar_setup": AvatarSetupState,
            "browse_lobby": BrowseLobbyState,
            "host_lobby": HostLobbyState,
            "joined_lobby": JoinedLobbyState,
            "in_game": InGameState,
            "results": ResultsState,
        }

    def change(self, state_name: str, **kwargs):
        if self.current_state is not None:
            self.current_state.exit()
        self.context.presence_status = PRESENCE_BY_STATE.get(state_name, protocol.PRESENCE_STATUS_ONLINE)
        if self.context.network is not None:
            self.context.network.set_client_state(
                NETWORK_CLIENT_STATE_BY_STATE.get(state_name, protocol.CLIENT_STATE_LOBBY)
            )
        LOGGER.info("State change -> %s", state_name)
        state_cls = self.state_map[state_name]
        self.current_state = state_cls(self, self.context, **kwargs)
        self.current_state.enter()

    def run(self, initial_state: str = "menu"):
        self.context.start_presence()
        self.change(initial_state)
        while self.context.running:
            raw_dt = self.context.clock.tick(60) / 1000.0
            dt = min(raw_dt, MAX_FRAME_DT)
            use_internal = (
                self.context.display_manager is not None
                and self.current_state is not None
                and self.current_state.render_to_internal
            )
            self.context.update_mouse_pos(use_internal=use_internal)
            for event in pygame.event.get():
                event = self.context.to_render_event(event, use_internal=use_internal)
                self.current_state.handle_event(event)

            self.current_state.update(dt)
            self.context.tick_timers(dt)

            if self.context.display_manager is not None and use_internal:
                surface = self.context.display_manager.begin_frame()
            elif self.context.display_manager is not None:
                surface = self.context.display_manager.begin_window_frame()
            else:
                surface = self.context.screen
            self.current_state.draw(surface)
            if not self.current_state.suppress_internal_global_messages:
                self.context.draw_global_messages(surface)
            if self.context.display_manager is not None and use_internal:
                window_surface = self.context.display_manager.blit_internal_to_window()
                self.current_state.draw_window_overlay(window_surface)
                pygame.display.flip()
            elif self.context.display_manager is not None:
                self.context.display_manager.present_window()
            else:
                pygame.display.flip()

        if self.current_state is not None:
            self.current_state.exit()
        self.context.shutdown()
