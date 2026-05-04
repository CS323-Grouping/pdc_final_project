import time

import pygame

from network.discovery import LobbyBrowser
from network import network_handler as nw
from network import protocol
from states.common import ScreenState
from ui import animations as anim
from ui import components as ui
from ui.components import BadgeKind
from ui.theme import DEFAULT_THEME


class BrowseLobbyState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.browser = None
        self.back_button = ui.Button(pygame.Rect(0, 0, 140, 42), "Back")
        self.refresh_button = ui.Button(pygame.Rect(0, 0, 140, 42), "Refresh")
        self.host_button = ui.Button(pygame.Rect(0, 0, 170, 46), "Host Room")
        self.join_button = ui.Button(pygame.Rect(0, 0, 170, 46), "Join Room", False)
        self.room_rows: list = []
        self._card_seen: dict[tuple[str, int], float] = {}
        self._selected_room_key: tuple[str, int] | None = None
        self._back_h = False
        self._ref_h = False
        self._host_h = False
        self._join_h = False

    def enter(self):
        self.browser = LobbyBrowser(discovery_port=self.context.discovery_port)
        self.browser.start()
        self._card_seen.clear()
        self.context.set_status("Searching for LAN rooms…", duration=2.0)

    def exit(self):
        if self.browser is not None:
            self.browser.stop()
            self.browser = None

    def _layout(self):
        width, height = self.context.screen.get_size()
        self.back_button.rect.topleft = (16, 52)
        self.refresh_button.rect.topright = (width - 16, 52)
        self.host_button.rect.bottomleft = (24, height - 24)
        self.join_button.rect.bottomright = (width - 24, height - 24)

    def _can_reconnect(self, room) -> bool:
        if room.state not in (protocol.STATE_IN_GAME, protocol.STATE_PAUSED):
            return False
        ticket = self.context.reconnect_ticket
        if ticket is None:
            return True
        if ticket.addr != room.addr or ticket.port != room.game_port:
            return False
        if ticket.room_name and ticket.room_name != room.room_name:
            return False
        return True

    def _badge_info(self, room, reconnectable: bool = False) -> tuple[str, BadgeKind]:
        if reconnectable:
            return "RECONNECT", "reconnect"
        if room.state == protocol.STATE_PAUSED:
            return "PAUSED", "paused"
        if room.state == protocol.STATE_COUNTDOWN:
            return "STARTING", "starting"
        if room.state == protocol.STATE_IN_GAME:
            return "IN GAME", "ingame"
        if room.current_players >= room.max_players:
            return "FULL", "full"
        return "LOBBY", "lobby"

    def _joinable(self, room) -> bool:
        if self._can_reconnect(room):
            return True
        if room.state in (protocol.STATE_COUNTDOWN, protocol.STATE_IN_GAME, protocol.STATE_PAUSED):
            return False
        if room.current_players >= room.max_players:
            return False
        return True

    def _reconnect_room(self, room):
        ticket = self.context.reconnect_ticket
        net = nw.Network()
        if ticket is None:
            result = net.reconnect_to_room(
                room.addr,
                room.game_port,
                -1,
                0,
                self.context.player_name,
            )
            is_host = False
        else:
            result = net.reconnect_to_room(
                room.addr,
                room.game_port,
                ticket.player_id,
                ticket.session_token,
                ticket.player_name,
            )
            is_host = ticket.is_host
        if not result.ok:
            self.context.set_status("Reconnect failed. Use the same name before the slot expires.", duration=4.0)
            net.close()
            return

        self.context.attach_network(
            network_obj=net,
            is_host=is_host,
            room_name=result.room_name,
            start_pos=result.start_pos,
        )
        self.switch("in_game")

    def _join_room(self, room):
        net = nw.Network()
        result = net.connect_to_room(room.addr, room.game_port, self.context.player_name)
        if not result.ok:
            if result.reason_code == protocol.CONNO_REASON_COOLDOWN:
                if result.extra == protocol.UINT32_MAX:
                    self.context.set_banner("On cooldown — rejoin blocked for this session.", duration=6.0)
                else:
                    self.context.set_banner(
                        f"On cooldown — {result.extra} seconds remaining.",
                        duration=6.0,
                    )
                net.close()
                self.switch("menu")
                return
            if result.reason_code == protocol.CONNO_REASON_IN_GAME:
                self.context.set_status("Room is no longer joinable.", duration=3.0)
            elif result.reason_code == protocol.CONNO_REASON_FULL:
                self.context.set_status("Room is already full.", duration=3.0)
            else:
                self.context.set_status("Failed to join room.", duration=3.0)
            net.close()
            return

        self.context.attach_network(
            network_obj=net,
            is_host=False,
            room_name=result.room_name,
            start_pos=result.start_pos,
        )
        self.switch("joined_lobby")

    def _selected_room(self):
        if self._selected_room_key is None:
            return None
        for _rect, room, joinable, reconnectable in self.room_rows:
            if (room.addr, room.game_port) == self._selected_room_key:
                return room, joinable, reconnectable
        return None

    def _host_room(self):
        if not protocol.is_valid_player_name(self.context.player_name):
            self.context.set_status("Name must be 3-24 alphanumeric characters.", duration=3.0)
            return
        self.context.room_name = f"{self.context.player_name}Room"
        self.switch("host_lobby")

    def _join_selected_room(self):
        selected = self._selected_room()
        if selected is None:
            self.context.set_status("Select a room first.", duration=2.0)
            return
        room, joinable, reconnectable = selected
        if not joinable:
            self.context.set_status("Selected room is not joinable.", duration=2.0)
            return
        if reconnectable:
            self._reconnect_room(room)
        else:
            self._join_room(room)

    def handle_event(self, event):
        super().handle_event(event)
        self._layout()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.back_button.rect.collidepoint(event.pos):
                self.switch("menu")
                return
            if self.refresh_button.rect.collidepoint(event.pos):
                self.context.set_status("Refreshing room list…", duration=1.0)
                return
            if self.host_button.rect.collidepoint(event.pos):
                self._host_room()
                return
            if self.join_button.enabled and self.join_button.rect.collidepoint(event.pos):
                self._join_selected_room()
                return
            for rect, room, joinable, reconnectable in self.room_rows:
                _ = joinable, reconnectable
                if rect.collidepoint(event.pos):
                    self._selected_room_key = (room.addr, room.game_port)
                    return

    def update(self, dt: float):
        _ = dt
        self.room_rows = []
        if self.browser is None:
            return

        now = time.monotonic()
        snapshot = self.browser.snapshot()
        alive = {(r.addr, r.game_port) for r in snapshot}
        if self._selected_room_key is not None and self._selected_room_key not in alive:
            self._selected_room_key = None
        for key in list(self._card_seen.keys()):
            if key not in alive:
                del self._card_seen[key]
        for r in snapshot:
            key = (r.addr, r.game_port)
            if key not in self._card_seen:
                self._card_seen[key] = now

        width, _height = self.context.screen.get_size()
        y = 118
        for room in snapshot:
            row_rect = pygame.Rect(24, y, width - 48, 72)
            reconnectable = self._can_reconnect(room)
            joinable = self._joinable(room)
            self.room_rows.append((row_rect, room, joinable, reconnectable))
            y += 80

        mp = self.context.mouse_pos
        self._back_h = self.back_button.rect.collidepoint(mp)
        self._ref_h = self.refresh_button.rect.collidepoint(mp)
        self._host_h = self.host_button.rect.collidepoint(mp)
        self._join_h = self.join_button.rect.collidepoint(mp)
        selected = self._selected_room()
        self.join_button.enabled = selected is not None and selected[1]

    def draw(self, surface):
        super().draw(surface)
        self._layout()
        theme = DEFAULT_THEME

        title = self.context.title_font.render("Browse LAN rooms", True, theme.text)
        surface.blit(title, (24, 12))

        ui.draw_button(surface, self.context.small_font, self.back_button, theme, hovered=self._back_h)
        ui.draw_button(surface, self.context.small_font, self.refresh_button, theme, hovered=self._ref_h)
        ui.draw_button(surface, self.context.small_font, self.host_button, theme, hovered=self._host_h)
        ui.draw_button(surface, self.context.small_font, self.join_button, theme, hovered=self._join_h)

        if not self.room_rows:
            empty = self.context.font.render("No rooms found", True, theme.text_muted)
            surface.blit(empty, (24, 130))
            hint = self.context.small_font.render(
                "Host a room or wait for nearby LAN rooms to appear.",
                True,
                theme.text_muted,
            )
            surface.blit(hint, (24, 168))
            return

        now = time.monotonic()
        fonts = (self.context.small_font, self.context.tiny_font)
        for rect, room, joinable, reconnectable in self.room_rows:
            label, kind = self._badge_info(room, reconnectable)
            key = (room.addr, room.game_port)
            fade = anim.fade_in_progress(now - self._card_seen.get(key, now), 0.35)
            addr_line = f"{room.addr}:{room.game_port}"
            if reconnectable:
                addr_line = f"{addr_line}  ·  reserved slot"
            ui.draw_room_card(
                surface,
                fonts,
                rect,
                room.room_name,
                room.current_players,
                room.max_players,
                label,
                kind,
                joinable,
                fade,
                addr_line,
                theme,
            )
            if self._selected_room_key == key:
                pygame.draw.rect(surface, theme.border_focus, rect.inflate(6, 6), width=3, border_radius=10)
