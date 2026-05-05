from dataclasses import dataclass
import logging
from pathlib import Path
import queue
import subprocess
import sys
import time
from typing import Dict, Optional, Type

import pygame

from network import network_handler as nw
from ui import components as ui
from ui.theme import DEFAULT_THEME

from states.browse_lobby import BrowseLobbyState
from states.host_lobby import HostLobbyState
from states.in_game import InGameState
from states.joined_lobby import JoinedLobbyState
from states.menu import MainMenuState
from states.results import ResultsState

LOGGER = logging.getLogger(__name__)


@dataclass
class AppContext:
    screen: pygame.Surface
    clock: pygame.time.Clock
    log_level: str
    running: bool = True
    player_name: str = "Player123"
    room_name: str = "Room123"
    banner_message: str = ""
    banner_timer: float = 0.0
    status_message: str = ""
    status_timer: float = 0.0
    network: Optional[nw.Network] = None
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
    level_number: int = 1

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

    def draw_global_messages(self):
        width, _height = self.screen.get_size()
        if self.banner_message:
            ui.draw_banner_bar(self.screen, self.small_font, self.banner_message)
        if self.status_message:
            y = 34 if self.banner_message else 8
            status_surface = self.tiny_font.render(self.status_message, True, (255, 230, 120))
            self.screen.blit(status_surface, (8, y))

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
        self.network.start_receiver()

    def detach_network(self, send_disconnect: bool = True):
        if self.network is None:
            self.is_host = False
            self.roster = []
            self.countdown_remaining = None
            return
        try:
            if send_disconnect:
                self.network.disconnect()
        finally:
            self.network.stop_receiver()
            try:
                self.network.client.close()
            except OSError:
                pass
            self.network = None
            self.is_host = False
            self.roster = []
            self.countdown_remaining = None

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
            dt = self.context.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                self.current_state.handle_event(event)

            self.current_state.update(dt)
            self.context.tick_timers(dt)

            self.current_state.draw(self.context.screen)
            self.context.draw_global_messages()
            pygame.display.flip()

        if self.current_state is not None:
            self.current_state.exit()
        self.context.shutdown()
