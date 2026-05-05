import math

import pygame

from network import network_handler as nw
from states.common import ScreenState, unique_roster
from ui import animations as anim
from ui import components as ui
from ui.theme import DEFAULT_THEME


def _host_player_id(roster: list) -> int | None:
    if not roster:
        return None
    return min(entry[0] for entry in roster)


class JoinedLobbyState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.ready_button = ui.Button(pygame.Rect(0, 0, 170, 46), "Ready")
        self.leave_button = ui.Button(pygame.Rect(0, 0, 150, 46), "Leave")
        self._ready_on = False
        self._pulse_t = 0.0
        self._roster_ids: frozenset[int] = frozenset()
        self._row_flash: dict[int, float] = {}
        self._ready_h = self._leave_h = False

    def enter(self):
        self._ready_on = False
        self._pulse_t = 0.0
        self._row_flash.clear()
        self._roster_ids = frozenset()
        net = self.context.network
        if net is None:
            return
        r = self.local_player_ready()
        if r is not None:
            self._ready_on = r
        if self.context.roster:
            self._roster_ids = frozenset(p[0] for p in self.context.roster)

    def _layout(self):
        w, h = self.context.screen.get_size()
        self.ready_button.rect.topleft = (w // 2 - 165, h - 58)
        self.leave_button.rect.topleft = (w // 2 + 15, h - 58)

    def _note_roster_change(self, entries: list) -> None:
        new_ids = frozenset(p[0] for p in entries)
        for pid in new_ids - self._roster_ids:
            self._row_flash[pid] = 1.0
        for pid in self._roster_ids - new_ids:
            self._row_flash[pid] = 0.35
        self._roster_ids = new_ids

    def _drain_network(self):
        for event in self.context.drain_network_events():
            if self.handle_common_network_event(event):
                continue
            if isinstance(event, nw.RosterEvent):
                entries = unique_roster(event.entries)
                self._note_roster_change(entries)
                self.context.roster = entries
                lr = self.local_player_ready()
                if lr is not None:
                    self._ready_on = lr
            elif isinstance(event, nw.CountdownEvent):
                self.context.countdown_remaining = event.seconds_until_start
            elif isinstance(event, nw.CountdownCancelEvent):
                self.context.countdown_remaining = None
            elif isinstance(event, nw.GameStartEvent):
                self.switch("in_game")
                return
            elif isinstance(event, nw.GameEndEvent):
                self.context.results_standings = list(event.standings)
                self.context.return_state_after_results = "joined_lobby"
                self.switch("results")
                return

    def handle_event(self, event):
        super().handle_event(event)
        self._layout()
        if self.context.network is None:
            self.switch("menu")
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.leave_button.rect.collidepoint(event.pos):
                self.context.detach_network(send_disconnect=True)
                self.switch("browse_lobby")
                return
            if self.ready_button.enabled and self.ready_button.rect.collidepoint(event.pos):
                self._ready_on = not self._ready_on
                self.context.network.send_ready(self._ready_on)

    def update(self, dt: float):
        self._pulse_t += dt
        self._drain_network()
        self.ready_button.enabled = self.context.network is not None
        for k in list(self._row_flash.keys()):
            self._row_flash[k] = anim.highlight_decay(self._row_flash[k], dt, rate=3.0)
            if self._row_flash[k] <= 0.01:
                del self._row_flash[k]
        mp = pygame.mouse.get_pos()
        self._ready_h = self.ready_button.rect.collidepoint(mp)
        self._leave_h = self.leave_button.rect.collidepoint(mp)

    def draw(self, surface):
        super().draw(surface)
        self._layout()
        theme = DEFAULT_THEME

        title = self.context.font.render(f"{self.context.room_name}", True, theme.text)
        surface.blit(title, (20, 20))
        sub = self.context.small_font.render("Waiting for host…", True, theme.text_muted)
        surface.blit(sub, (20, 48))

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
        elif not self._ready_on and self.ready_button.rect.collidepoint(pygame.mouse.get_pos()):
            ui.draw_tooltip(
                surface,
                self.context.tiny_font,
                "Toggle Ready so the host can start.",
                self.ready_button.rect.topleft,
                theme,
            )

        hid = _host_player_id(self.context.roster)
        y = 112
        for player_id, ready, name in self.context.roster:
            tag = ""
            if hid is not None and player_id == hid:
                tag = " · HOST"
            line = f"{name}{tag}  ·  {'READY' if ready else 'not ready'}"
            row_rect = pygame.Rect(20, y, surface.get_width() - 40, 42)
            flash = self._row_flash.get(player_id, 0.0)
            ui.draw_roster_row(surface, self.context.small_font, row_rect, line, flash, theme=theme)
            y += 50

        self.ready_button.text = "Unready" if self._ready_on else "Ready"
        glow = anim.pulse01(self._pulse_t, 1.0) if self._ready_on else 0.0
        if glow > 0.52 and self._ready_on:
            gr = self.ready_button.rect.inflate(6, 4)
            s = pygame.Surface((gr.w, gr.h), pygame.SRCALPHA)
            pygame.draw.rect(s, (80, 140, 220, int(40 * (glow - 0.5) * 2)), s.get_rect(), border_radius=8)
            surface.blit(s, gr.topleft)
        ui.draw_button(surface, self.context.small_font, self.ready_button, theme, hovered=self._ready_h)

        ui.draw_button(
            surface,
            self.context.small_font,
            self.leave_button,
            theme,
            variant="neutral",
            hovered=self._leave_h,
        )
