import pygame

from network import network_handler as nw
from states.common import ScreenState
from ui import animations as anim
from states.room_lobby_ui import RoomLobbyUi


def _host_player_id(roster: list) -> int | None:
    if not roster:
        return None
    return min(entry[0] for entry in roster)


class JoinedLobbyState(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self._ready_on = False
        self._pulse_t = 0.0
        self._heartbeat_elapsed = 0.0
        self._server_silence_elapsed = 0.0
        self._roster_ids: frozenset[int] = frozenset()
        self._row_flash: dict[int, float] = {}
        self._hovered = None
        self._room_ui = RoomLobbyUi(context)

    def enter(self):
        self._room_ui.enter()
        self._ready_on = False
        self._pulse_t = 0.0
        self._heartbeat_elapsed = 0.0
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

    def _drain_network(self):
        heard_server = False
        my_id = self.context.network.id if self.context.network else -1
        for event in self.context.drain_network_events():
            heard_server = True
            if self.handle_common_network_event(event):
                return True
            if self._room_ui.handle_avatar_event(event, my_id):
                continue
            if isinstance(event, nw.RosterEvent):
                entries = list(event.entries)
                old_ids = set(self._roster_ids)
                new_ids = {player_id for player_id, _ready, _name in entries}
                self._note_roster_change(entries)
                if new_ids - old_ids:
                    self._room_ui.restart_avatar_broadcast()
                self.context.roster = entries
                self._room_ui.retain_remote_avatars(new_ids)
                lr = self.local_player_ready()
                if lr is not None:
                    self._ready_on = lr
            elif isinstance(event, nw.CountdownEvent):
                self.context.countdown_remaining = event.seconds_until_start
            elif isinstance(event, nw.CountdownCancelEvent):
                self.context.countdown_remaining = None
            elif isinstance(event, nw.RoomNameEvent):
                self.context.room_name = event.room_name
            elif isinstance(event, nw.GameStartEvent):
                self.context.countdown_remaining = None
                self.switch("in_game")
                return True
            elif isinstance(event, nw.GameEndEvent):
                self.context.reset_lobby_after_game()
                self._ready_on = False
                self.context.results_standings = list(event.standings)
                self.context.return_state_after_results = "joined_lobby"
                self.switch("results")
                return True
        return heard_server

    def handle_event(self, event):
        super().handle_event(event)
        if self.context.network is None:
            self.switch("menu")
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
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
                if action == "secondary":
                    self._leave_room()
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
        self._heartbeat_elapsed += dt
        if self._heartbeat_elapsed >= 1.0:
            self._heartbeat_elapsed = 0.0
            self.context.network.send_ready(self._ready_on)
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
        )
