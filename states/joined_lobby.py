import pygame

from states.common import host_player_id as _host_player_id
from states.lobby_base import LobbyStateBase
from ui import animations as anim


class JoinedLobbyState(LobbyStateBase):
    return_state_after_results = "joined_lobby"

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self._ready_on = False
        self._pulse_t = 0.0
        self._server_silence_elapsed = 0.0
        self._roster_ids: frozenset[int] = frozenset()
        self._row_flash: dict[int, float] = {}
        self._hovered = None

    def enter(self):
        self._room_ui.enter()
        self._ready_on = False
        self._pulse_t = 0.0
        self._server_silence_elapsed = 0.0
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

    def _note_roster_change(self, entries: list) -> None:
        new_ids = frozenset(p[0] for p in entries)
        for pid in new_ids - self._roster_ids:
            self._row_flash[pid] = 1.0
        for pid in self._roster_ids - new_ids:
            self._row_flash[pid] = 0.35
        self._roster_ids = new_ids

    def _leave_room(self) -> None:
        self.context.detach_network(send_disconnect=True)
        self.switch("browse_lobby")

    # ---- LobbyStateBase hooks --------------------------------------------
    def _on_roster_about_to_change(self, entries, old_ids, new_ids) -> None:
        self._note_roster_change(entries)

    def _on_roster_changed(self, entries, old_ids, new_ids) -> None:
        lr = self.local_player_ready()
        if lr is not None:
            self._ready_on = lr

    def _on_game_end(self) -> None:
        self._ready_on = False

    def handle_event(self, event):
        super().handle_event(event)
        if self.context.network is None:
            self.switch("menu")
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.context.countdown_remaining is not None:
                return
            self._leave_room()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = self._room_ui.hit_test(
                event.pos,
                self.context.roster,
                _host_player_id(self.context.roster),
                host_view=False,
                kick_mode=False,
            )
            if self.context.countdown_remaining is not None:
                return
            if action == "secondary":
                self._leave_room()
                return
            if action == "primary":
                self._ready_on = not self._ready_on
                self.context.network.send_ready(self._ready_on)

    def update(self, dt: float):
        self._pulse_t += dt
        if self._drain_network():
            self._server_silence_elapsed = 0.0
        else:
            self._server_silence_elapsed += dt
        if self.context.network is None:
            return
        if self._server_silence_elapsed >= 4.0:
            self.context.set_banner("Host closed the room or stopped responding.", duration=5.0)
            self.context.detach_network(send_disconnect=False, preserve_reconnect=True)
            self.switch("browse_lobby")
            return
        self._room_ui.update(dt, self.context.network)
        for k in list(self._row_flash.keys()):
            self._row_flash[k] = anim.highlight_decay(self._row_flash[k], dt, rate=3.0)
            if self._row_flash[k] <= 0.01:
                del self._row_flash[k]
        mp = self.context.mouse_pos
        self._hovered = self._room_ui.hit_test(
            mp,
            self.context.roster,
            _host_player_id(self.context.roster),
            host_view=False,
            kick_mode=False,
        )
        if self.context.countdown_remaining is not None:
            self._hovered = None

    def draw(self, surface):
        hid = _host_player_id(self.context.roster)
        self._room_ui.draw_base(
            surface,
            self.context.roster,
            host_id=hid,
            host_view=False,
            kick_mode=False,
            hovered=self._hovered,
            primary_enabled=self.context.network is not None,
        )

    def draw_window_overlay(self, surface: pygame.Surface):
        network = self.context.network
        local_id = network.id if network is not None else None
        self._room_ui.draw_window_overlay(
            surface,
            self.context.roster,
            room_name=self.context.room_name,
            host_id=_host_player_id(self.context.roster),
            local_player_id=local_id,
            host_view=False,
            kick_mode=False,
            primary_enabled=self.context.network is not None,
            primary_label="NOT READY" if self._ready_on else "READY",
            secondary_label="LEAVE",
            countdown_remaining=self.context.countdown_remaining,
            pulse_t=self._pulse_t,
            selected_level=self.context.selected_level,
        )
