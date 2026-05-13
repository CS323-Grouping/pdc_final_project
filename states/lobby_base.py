"""Common scaffolding for ``HostLobbyState`` and ``JoinedLobbyState``.

The two lobby screens share almost all of their network-event drain logic
(roster, avatars, countdown, game-start/end). The remaining differences (host
kick UI, joined ready state + server-silence detection) are exposed via
template-method hooks below.
"""

from __future__ import annotations

import pygame

from network import network_handler as nw
from states.common import ScreenState
from states.room_lobby_ui import RoomLobbyUi


class LobbyStateBase(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

    # Subclass overrides: which screen to return to after a results screen.
    return_state_after_results: str = ""

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self._room_ui = RoomLobbyUi(context)

    # ------------------------------------------------------------------ drain
    def _drain_network(self) -> bool:
        """Process queued network events; returns True if any were seen."""
        heard_server = False
        my_id = self.context.network.id if self.context.network else -1
        for event in self.context.drain_network_events():
            heard_server = True
            if self.handle_common_network_event(event):
                if self.context.network is None:
                    return True
                continue
            if self._room_ui.handle_avatar_event(event, my_id):
                continue
            if isinstance(event, nw.RosterEvent):
                self._handle_roster_event(event)
            elif isinstance(event, nw.CountdownEvent):
                self.accept_countdown_event(event)
            elif isinstance(event, nw.CountdownCancelEvent):
                self.accept_countdown_cancel_event(event)
            elif isinstance(event, nw.RoomNameEvent):
                self.context.room_name = event.room_name
            elif isinstance(event, nw.GameStartEvent):
                if not self.accept_game_start_event(event):
                    continue
                self.switch("in_game")
                return True
            elif isinstance(event, nw.GameEndEvent):
                if not self.accept_game_end_event(event):
                    continue
                self.context.reset_lobby_after_game()
                self._on_game_end()
                self.context.results_standings = list(event.standings)
                self.context.return_state_after_results = self.return_state_after_results
                self.switch("results")
                return True
            else:
                self._handle_extra_event(event)
        return heard_server

    def _handle_roster_event(self, event: nw.RosterEvent) -> None:
        entries = list(event.entries)
        old_ids = {player_id for player_id, _ready, _name in self.context.roster}
        new_ids = {player_id for player_id, _ready, _name in entries}
        self._on_roster_about_to_change(entries, old_ids, new_ids)
        if new_ids - old_ids:
            self._room_ui.restart_avatar_broadcast()
        self.context.roster = entries
        self._room_ui.retain_remote_avatars(new_ids)
        self._on_roster_changed(entries, old_ids, new_ids)

    # ----------------------------------------------------------------- hooks
    def _on_roster_about_to_change(self, entries, old_ids, new_ids) -> None:
        """Subclass hook fired before ``self.context.roster`` is replaced."""

    def _on_roster_changed(self, entries, old_ids, new_ids) -> None:
        """Subclass hook fired after the new roster + avatar cleanup are applied."""

    def _on_game_end(self) -> None:
        """Subclass hook fired after a GameEndEvent is accepted, before switching to results."""

    def _handle_extra_event(self, event) -> None:
        """Subclass hook for any event types not handled by the base drain."""
