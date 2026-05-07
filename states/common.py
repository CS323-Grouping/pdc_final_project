from typing import Optional

import pygame

from network import network_handler as nw
from network import protocol
from ui.theme import DEFAULT_THEME


class ScreenState:
    render_to_internal = False
    suppress_internal_global_messages = False

    def __init__(self, machine, context, **kwargs):
        self.machine = machine
        self.context = context
        self.kwargs = kwargs

    def enter(self):
        pass

    def exit(self):
        pass

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.context.running = False

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        surface.fill(DEFAULT_THEME.bg)

    def draw_window_overlay(self, surface: pygame.Surface):
        pass

    def switch(self, state_name: str, **kwargs):
        self.machine.change(state_name, **kwargs)

    def _kicked_banner_message(self, reason_code: int) -> str:
        if reason_code == protocol.KICKED_REASON_KICKED:
            return "Host removed you from the room."
        if reason_code == protocol.KICKED_REASON_ROOM_CLOSED:
            return "Host closed the room."
        if reason_code == protocol.KICKED_REASON_NOT_READY:
            return "Removed: you were not ready at countdown end."
        return "Disconnected from room."

    def handle_common_network_event(self, event) -> bool:
        if isinstance(event, nw.SessionEvent):
            self.context.remember_reconnect_ticket()
            return True
        if isinstance(event, nw.ConnectionLostEvent):
            message = event.message
            if "WinError 10054" in message or "forcibly closed" in message:
                message = "Host closed the room or the connection was lost."
            self.context.set_banner(message, duration=5.0)
            self.context.detach_network(send_disconnect=False, preserve_reconnect=True)
            self.switch("browse_lobby" if self.context.reconnect_ticket is not None else "menu")
            return True
        if isinstance(event, nw.KickedEvent):
            self.context.set_banner(self._kicked_banner_message(event.reason_code))
            self.context.detach_network(send_disconnect=False)
            self.context.stop_server()
            self.switch("menu")
            return True
        if isinstance(event, nw.ErrorEvent):
            self.context.set_status(event.message, duration=2.0)
            return True
        return False

    def host_and_non_host_ready(self) -> bool:
        roster = self.context.roster
        if len(roster) < protocol.MIN_PLAYERS:
            return False
        network = self.context.network
        if network is None:
            return False
        for player_id, ready, _name in roster:
            if player_id == network.id:
                continue
            if not ready:
                return False
        return True

    def local_player_ready(self) -> Optional[bool]:
        network = self.context.network
        if network is None:
            return None
        for player_id, ready, _name in self.context.roster:
            if player_id == network.id:
                return ready
        return None


def filter_player_name_input(value: str) -> str:
    return protocol.sanitize_player_name_input(value)


def filter_room_name_input(value: str) -> str:
    return protocol.sanitize_room_name_input(value)


def event_has_ctrl_modifier(event) -> bool:
    return bool(getattr(event, "mod", 0) & pygame.KMOD_CTRL)


def get_clipboard_text() -> str:
    try:
        get_init = getattr(pygame.scrap, "get_init", None)
        if get_init is None or not get_init():
            pygame.scrap.init()
        raw = pygame.scrap.get(pygame.SCRAP_TEXT)
    except (AttributeError, pygame.error):
        return ""
    if not raw:
        return ""
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="ignore")
    else:
        text = str(raw)
    return text.replace("\x00", "").replace("\r", "").replace("\n", "")


def remove_previous_input_token(value: str, separators: str = " _-.") -> str:
    end = len(value)
    while end > 0 and value[end - 1] in separators:
        end -= 1
    while end > 0 and value[end - 1] not in separators:
        end -= 1
    return value[:end]
