import math
from typing import Optional

import pygame

from network import network_handler as nw
from network import protocol
import time
from states.common import ScreenState, alnum_only, unique_roster
from ui import components as ui
from ui.theme import DEFAULT_THEME


def _host_player_id(roster: list) -> int | None:
    if not roster:
        return None
    return min(entry[0] for entry in roster)


class HostLobbyState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.room_active = False
        self.room_input = context.room_name or "HostRoom"
        self.open_button = ui.Button(pygame.Rect(0, 0, 200, 46), "Open Room")
        self.start_button = ui.Button(pygame.Rect(0, 0, 200, 46), "Start")
        self.cancel_button = ui.Button(pygame.Rect(0, 0, 220, 46), "Cancel Countdown")
        self.close_button = ui.Button(pygame.Rect(0, 0, 180, 46), "Close Room")
        self.room_rect = pygame.Rect(0, 0, 360, 44)
        self.kick_rects: list[tuple[pygame.Rect, int, str]] = []
        self._session_open = False
        self._confirm: Optional[ui.ConfirmDialog] = None
        self._pulse_t = 0.0
        self._open_h = self._start_h = self._cancel_h = self._close_h = False
        self._kick_hover: Optional[int] = None

    def enter(self):
        net = self.context.network
        self._session_open = net is not None and net.id >= 0
        self._confirm = None
        if not self._session_open:
            self.room_input = self.context.room_name or self.room_input

    def _cancel_dialog(self) -> None:
        self._confirm = None

    def _layout_setup(self):
        w, h = self.context.screen.get_size()
        self.room_rect.center = (w // 2, h // 2 - 40)
        self.open_button.rect.center = (w // 2, h // 2 + 36)

    def _layout_session(self):
        w, h = self.context.screen.get_size()
        self.start_button.rect.topright = (w - 16, 16)
        self.cancel_button.rect.topright = (w - 16, 16)
        self.close_button.rect.topleft = (16, h - 58)

    def _open_room(self):
        name = self.room_input.strip()
        if not protocol.is_valid_room_name(name):
            self.context.set_status("Room name must be 3–24 alphanumeric characters.", duration=3.0)
            return
        self.context.room_name = name
        if not self.context.start_local_server(name):
            self.context.set_status("Could not start server (port in use or server exited).", duration=4.0)
            return
        net = nw.Network()
        # Give server more startup time
        time.sleep(0.8)
        result = net.connect_to_room(
            self.context.server_host,
            self.context.server_port,
            self.context.player_name,
        )
        if not result.ok:
            self.context.stop_server()
            self.context.set_status("Failed to connect to local server.", duration=3.0)
            try:
                net.client.close()
            except OSError:
                pass
            return
        self.context.attach_network(net, is_host=True, room_name=result.room_name, start_pos=result.start_pos)
        self._session_open = True

    def _perform_close_room(self) -> None:
        if self.context.network:
            self.context.network.close_room()
        self.context.stop_server()
        self.context.detach_network(send_disconnect=False)
        self._session_open = False
        self._cancel_dialog()
        self.switch("menu")

    def _start_disable_reason(self) -> str:
        roster = self.context.roster
        if len(roster) < protocol.MIN_PLAYERS:
            return "Need at least two players in the room to start."
        hid = _host_player_id(roster)
        for pid, ready, name in roster:
            if hid is not None and pid == hid:
                continue
            if not ready:
                return f"Waiting for {name} to ready up."
        return ""

    def _drain_network(self):
        for event in self.context.drain_network_events():
            if self.handle_common_network_event(event):
                continue
            if isinstance(event, nw.RosterEvent):
                self.context.roster = unique_roster(event.entries)
            elif isinstance(event, nw.CountdownEvent):
                self.context.countdown_remaining = event.seconds_until_start
            elif isinstance(event, nw.CountdownCancelEvent):
                self.context.countdown_remaining = None
            elif isinstance(event, nw.GameStartEvent):
                self.switch("in_game")
                return
            elif isinstance(event, nw.GameEndEvent):
                self.context.results_standings = list(event.standings)
                self.context.return_state_after_results = "host_lobby"
                self.switch("results")
                return

    def handle_event(self, event):
        super().handle_event(event)
        if self._confirm is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                w, h = self.context.screen.get_size()
                _box, yes_r, no_r = self._confirm.layout(w, h)
                self._confirm.handle_click(event.pos, yes_r, no_r)
            return

        if not self._session_open:
            self._layout_setup()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.room_active = self.room_rect.collidepoint(event.pos)
                if self.open_button.enabled and self.open_button.rect.collidepoint(event.pos):
                    self._open_room()
            if event.type == pygame.KEYDOWN and self.room_active:
                if event.key == pygame.K_BACKSPACE:
                    self.room_input = self.room_input[:-1]
                else:
                    self.room_input = alnum_only(self.room_input + event.unicode, max_len=24)
            return

        self._layout_session()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.close_button.rect.collidepoint(event.pos):

                def go():
                    self._perform_close_room()

                self._confirm = ui.ConfirmDialog(
                    title="Close room?",
                    message="All players will be disconnected and the server will stop.",
                    on_confirm=go,
                    on_cancel=self._cancel_dialog,
                    confirm_label="Close",
                    cancel_label="Cancel",
                )
                return

            in_cd = self.context.countdown_remaining is not None
            if in_cd:
                if self.cancel_button.enabled and self.cancel_button.rect.collidepoint(event.pos):
                    self.context.network.cancel_countdown()
            else:
                if self.start_button.enabled and self.start_button.rect.collidepoint(event.pos):
                    self.context.network.send_start()

            for rect, pid, pname in self.kick_rects:
                if rect.collidepoint(event.pos):

                    def make_kick(target_id: int):
                        def _inner():
                            if self.context.network:
                                self.context.network.send_kick(target_id)
                            self._cancel_dialog()

                        return _inner

                    self._confirm = ui.ConfirmDialog(
                        title="Kick player?",
                        message=f"Remove {pname} from this room?",
                        on_confirm=make_kick(pid),
                        on_cancel=self._cancel_dialog,
                        confirm_label="Kick",
                        cancel_label="Cancel",
                    )
                    break

    def update(self, dt: float):
        self._pulse_t += dt
        mp = pygame.mouse.get_pos()
        if self._confirm is not None:
            return
        if self._session_open:
            self._drain_network()
            in_cd = self.context.countdown_remaining is not None
            self.start_button.enabled = (not in_cd) and self.host_and_non_host_ready()
            self.cancel_button.enabled = in_cd
            self.close_button.enabled = True
            self._layout_session()
            self._start_h = self.start_button.rect.collidepoint(mp) and self.start_button.enabled
            self._cancel_h = self.cancel_button.rect.collidepoint(mp) and self.cancel_button.enabled
            self._close_h = self.close_button.rect.collidepoint(mp)
            self._kick_hover = None
            for rect, pid, _name in self.kick_rects:
                if rect.collidepoint(mp):
                    self._kick_hover = pid
        else:
            self._layout_setup()
            self.open_button.enabled = protocol.is_valid_room_name(self.room_input)
            self._open_h = self.open_button.rect.collidepoint(mp)

    def draw(self, surface):
        super().draw(surface)
        theme = DEFAULT_THEME

        if self._confirm is not None:
            fonts = (self.context.title_font, self.context.font, self.context.small_font)
            self._confirm.draw(surface, fonts, theme)
            return

        if not self._session_open:
            self._layout_setup()
            title = self.context.title_font.render("Host a room", True, theme.text)
            surface.blit(title, title.get_rect(center=(surface.get_width() // 2, 76)))

            inp = ui.TextInput(self.room_rect, "Room name (alphanumeric, 3–24)", self.room_input, self.room_active)
            ui.draw_text_input(surface, (self.context.font, self.context.tiny_font), inp, theme)

            if not protocol.is_valid_room_name(self.room_input):
                warn = self.context.tiny_font.render(
                    "Room name must be 3–24 alphanumeric characters.",
                    True,
                    theme.text_warn,
                )
                surface.blit(warn, (self.room_rect.x, self.room_rect.y + self.room_rect.height + 8))

            ui.draw_button(surface, self.context.small_font, self.open_button, theme, hovered=self._open_h)
            return

        self._layout_session()
        hdr = self.context.font.render(f"Hosting: {self.context.room_name}", True, theme.text)
        surface.blit(hdr, (16, 22))

        if self.context.countdown_remaining is not None:
            sec = max(0, int(math.ceil(max(0.0, self.context.countdown_remaining))))
            ui.draw_countdown_overlay(
                surface,
                self.context.title_font,
                self.context.small_font,
                sec,
                self._pulse_t,
                theme,
            )
            ui.draw_button(surface, self.context.small_font, self.cancel_button, theme, hovered=self._cancel_h)
        else:
            ui.draw_button(surface, self.context.small_font, self.start_button, theme, hovered=self._start_h)
            if not self.start_button.enabled and self.start_button.rect.collidepoint(pygame.mouse.get_pos()):
                ui.draw_tooltip(
                    surface,
                    self.context.tiny_font,
                    self._start_disable_reason(),
                    self.start_button.rect.bottomleft,
                    theme,
                )

        ui.draw_button(surface, self.context.small_font, self.close_button, theme, variant="danger", hovered=self._close_h)

        y = 118
        hid = _host_player_id(self.context.roster)
        self.kick_rects = []
        row_font = self.context.small_font
        for player_id, ready, name in self.context.roster:
            tag = ""
            if hid is not None and player_id == hid:
                tag = " · HOST"
            line = f"{name}{tag}  ·  {'READY' if ready else 'not ready'}"
            row_rect = pygame.Rect(20, y, surface.get_width() - 40, 40)
            ui.draw_roster_row(surface, row_font, row_rect, line, highlight=0.0, theme=theme)
            if hid is not None and player_id != hid:
                kick = pygame.Rect(row_rect.right - 108, row_rect.y + 6, 96, 28)
                kh = self._kick_hover == player_id
                ui.draw_button(
                    surface,
                    self.context.tiny_font,
                    ui.Button(kick, "Kick", True),
                    theme,
                    hovered=kh,
                    variant="danger",
                )
                self.kick_rects.append((kick, player_id, name))
            y += 48
