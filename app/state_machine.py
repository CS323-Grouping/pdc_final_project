from dataclasses import dataclass
import logging
from pathlib import Path
import queue
import subprocess
import sys
import time
from typing import Dict, Optional, Type

import pygame

from app.display import DisplayConfig, DisplayManager
from network import network_handler as nw
from ui import components as ui
from ui.theme import DEFAULT_THEME

from states.avatar_setup import AvatarSetupState
from states.browse_lobby import BrowseLobbyState
from states.host_lobby import HostLobbyState
from states.in_game import InGameState
from states.joined_lobby import JoinedLobbyState
from states.menu import MainMenuState
from states.results import ResultsState

LOGGER = logging.getLogger(__name__)
MAX_FRAME_DT = 1.0 / 30.0


@dataclass
class ReconnectTicket:
    addr: str
    port: int
    room_name: str
    player_id: int
    session_token: int
    player_name: str
    is_host: bool


@dataclass
class AppContext:
    screen: pygame.Surface
    clock: pygame.time.Clock
    log_level: str
    display_manager: Optional[DisplayManager] = None
    running: bool = True
    player_name: str = "Player123"
    room_name: str = "Room123"
    banner_message: str = ""
    banner_timer: float = 0.0
    status_message: str = ""
    status_timer: float = 0.0
    avatar_surface: Optional[pygame.Surface] = None
    avatar_window_surface: Optional[pygame.Surface] = None
    avatar_source_name: str = "Default avatar"
    network: Optional[nw.Network] = None
    reconnect_ticket: Optional[ReconnectTicket] = None
    is_host: bool = False
    server_process: Optional[subprocess.Popen] = None
    server_host: str = "127.0.0.1"
    server_port: int = 5555
    discovery_port: int = 5556
    roster: list = None
    countdown_remaining: Optional[float] = None
    start_pos: tuple = (100.0, 100.0)
    results_standings: list = None
    return_state_after_results: str = "joined_lobby"
    mouse_pos: tuple[int, int] = (0, 0)

    def __post_init__(self):
        t = DEFAULT_THEME
        self.font = pygame.font.SysFont(t.font_body, t.size_large)
        self.small_font = pygame.font.SysFont(t.font_body, t.size_small)
        self.tiny_font = pygame.font.SysFont(t.font_body, t.size_tiny)
        self.title_font = pygame.font.SysFont(t.font_title, t.size_title)
        self.project_root = Path(__file__).resolve().parents[1]
        if self.roster is None:
            self.roster = []
        if self.results_standings is None:
            self.results_standings = []

    def set_banner(self, message: str, duration: float = 4.0):
        self.banner_message = message
        self.banner_timer = duration

    def set_status(self, message: str, duration: float = 3.0):
        self.status_message = message
        self.status_timer = duration

    def tick_timers(self, dt: float):
        if self.banner_timer > 0:
            self.banner_timer = max(0.0, self.banner_timer - dt)
            if self.banner_timer == 0:
                self.banner_message = ""
        if self.status_timer > 0:
            self.status_timer = max(0.0, self.status_timer - dt)
            if self.status_timer == 0:
                self.status_message = ""
        if self.countdown_remaining is not None:
            self.countdown_remaining = max(0.0, self.countdown_remaining - dt)

    def draw_global_messages(self, surface: Optional[pygame.Surface] = None):
        surface = surface or self.screen
        if self.banner_message:
            ui.draw_banner_bar(surface, self.small_font, self.banner_message)
        if self.status_message:
            y = 34 if self.banner_message else 8
            status_surface = self.tiny_font.render(self.status_message, True, (255, 230, 120))
            surface.blit(status_surface, (8, y))

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
        if hasattr(event, "pos"):
            attrs = dict(event.__dict__)
            attrs["pos"] = self.display_manager.window_to_internal(event.pos)
            return pygame.event.Event(event.type, attrs)
        return event

    def start_local_server(self, room_name: str) -> bool:
        self.stop_server()
        command = [
            sys.executable,
            str(self.project_root / "network" / "server.py"),
            "--host",
            "0.0.0.0",
            "--port",
            str(self.server_port),
            "--discovery-port",
            str(self.discovery_port),
            "--room",
            room_name,
            "--log-level",
            self.log_level,
        ]
        self.server_process = subprocess.Popen(command, cwd=str(self.project_root))
        time.sleep(0.4)
        if self.server_process.poll() is not None:
            self.server_process = None
            return False
        return True

    def stop_server(self):
        if self.server_process is None:
            return
        if self.server_process.poll() is None:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        self.server_process = None

    def attach_network(self, network_obj: nw.Network, is_host: bool, room_name: str, start_pos):
        self.detach_network(send_disconnect=False)
        self.network = network_obj
        self.is_host = is_host
        self.room_name = room_name
        self.start_pos = start_pos or (100.0, 100.0)
        self.roster = []
        self.countdown_remaining = None
        self.results_standings = []
        self.remember_reconnect_ticket()
        self.network.start_receiver()

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
                self.network.disconnect()
        finally:
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
        self.detach_network(send_disconnect=True)
        self.stop_server()


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
        state_cls = self.state_map[state_name]
        self.current_state = state_cls(self, self.context, **kwargs)
        self.current_state.enter()

    def run(self, initial_state: str = "menu"):
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
