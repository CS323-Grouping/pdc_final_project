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
        self.room_rows: list = []
        self._card_seen: dict[tuple[str, int], float] = {}
        self._back_h = False
        self._ref_h = False

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
        width, _height = self.context.screen.get_size()
        self.back_button.rect.topleft = (16, 52)
        self.refresh_button.rect.topright = (width - 16, 52)

    def _can_reconnect(self, room) -> bool:
        ticket = self.context.reconnect_ticket
        if ticket is None:
            return False
        if ticket.addr != room.addr or ticket.port != room.game_port:
            return False
        if ticket.room_name and ticket.room_name != room.room_name:
            return False
        return room.state in (protocol.STATE_IN_GAME, protocol.STATE_PAUSED)

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
        if ticket is None:
            self.context.set_status("No reconnect slot is available.", duration=3.0)
            return
        net = nw.Network()
        result = net.reconnect_to_room(
            room.addr,
            room.game_port,
            ticket.player_id,
            ticket.session_token,
            ticket.player_name,
        )
        if not result.ok:
            self.context.set_status("Reconnect failed or the slot expired.", duration=4.0)
            net.close()
            return

        self.context.attach_network(
            network_obj=net,
            is_host=ticket.is_host,
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
            for rect, room, joinable, reconnectable in self.room_rows:
                if rect.collidepoint(event.pos) and joinable:
                    if reconnectable:
                        self._reconnect_room(room)
                    else:
                        self._join_room(room)
                    return

    def update(self, dt: float):
        _ = dt
        self.room_rows = []
        if self.browser is None:
            return

        now = time.monotonic()
        snapshot = self.browser.snapshot()
        alive = {(r.addr, r.game_port) for r in snapshot}
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

    def draw(self, surface):
        super().draw(surface)
        self._layout()
        theme = DEFAULT_THEME

        title = self.context.title_font.render("Browse LAN rooms", True, theme.text)
        surface.blit(title, (24, 12))

        ui.draw_button(surface, self.context.small_font, self.back_button, theme, hovered=self._back_h)
        ui.draw_button(surface, self.context.small_font, self.refresh_button, theme, hovered=self._ref_h)

        if not self.room_rows:
            empty = self.context.font.render("No rooms found", True, theme.text_muted)
            surface.blit(empty, (24, 130))
            hint = self.context.small_font.render(
                "Wait for a host on your network or click Refresh. Check Windows Firewall for Python if nothing appears.",
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
