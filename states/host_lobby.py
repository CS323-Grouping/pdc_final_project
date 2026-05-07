from typing import Optional

import pygame

from network import network_handler as nw
from network import protocol
from states.common import ScreenState, event_has_ctrl_modifier, filter_room_name_input, remove_previous_input_token
from states.room_lobby_ui import RoomLobbyUi
from ui import components as ui
from ui.theme import DEFAULT_THEME


def _host_player_id(roster: list) -> int | None:
    if not roster:
        return None
    return min(entry[0] for entry in roster)


class HostLobbyState(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

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
        self._confirm_close_room = False
        self._confirm_hovered = None
        self._room_name_edit_open = False
        self._room_name_edit_field_active = False
        self._room_name_edit_original = context.room_name
        self._room_name_edit_value = context.room_name
        self._room_name_edit_hovered = None
        self._pulse_t = 0.0
        self._open_h = self._start_h = self._cancel_h = self._close_h = False
        self._kick_hover: Optional[int] = None
        self._kick_mode_on = False
        self._hovered = None
        self._room_ui = RoomLobbyUi(context)

    def enter(self):
        self._room_ui.enter()
        net = self.context.network
        self._session_open = net is not None and net.id >= 0
        self._confirm_close_room = False
        self._confirm_hovered = None
        self._room_name_edit_open = False
        self._room_name_edit_field_active = False
        self._room_name_edit_original = self.context.room_name
        self._room_name_edit_value = self.context.room_name
        self._room_name_edit_hovered = None
        self._kick_mode_on = False
        self._hovered = None
        if not self._session_open:
            self.room_input = self.context.room_name or self.room_input

    def _cancel_dialog(self) -> None:
        self._confirm_close_room = False
        self._confirm_hovered = None

    def _open_room_name_edit(self) -> None:
        self._room_name_edit_original = self.context.room_name
        self._room_name_edit_value = self.context.room_name
        self._room_name_edit_open = True
        self._room_name_edit_field_active = False
        self._room_name_edit_hovered = None

    def _close_room_name_edit(self) -> None:
        self._room_name_edit_open = False
        self._room_name_edit_field_active = False
        self._room_name_edit_hovered = None

    def _room_name_edit_save_enabled(self) -> bool:
        return (
            self._room_name_edit_value != self._room_name_edit_original
            and protocol.is_valid_room_name(self._room_name_edit_value)
        )

    def _save_room_name_edit(self) -> None:
        if not self._room_name_edit_save_enabled():
            return
        self.context.room_name = self._room_name_edit_value
        if self.context.network:
            self.context.network.room_name = self._room_name_edit_value
            self.context.network.send_room_name(self._room_name_edit_value)
        self._close_room_name_edit()

    def _render_size(self) -> tuple[int, int]:
        if self.context.display_manager is not None and self.render_to_internal:
            return self.context.display_manager.config.internal_size
        return self.context.screen.get_size()

    def _layout_setup(self):
        w, h = self._render_size()
        self.room_rect.center = (w // 2, h // 2 - 40)
        self.open_button.rect.center = (w // 2, h // 2 + 36)

    def _layout_session(self):
        w, h = self._render_size()
        self.start_button.rect.topright = (w - 16, 16)
        self.cancel_button.rect.topright = (w - 16, 16)
        self.close_button.rect.topleft = (16, h - 52)

    def _open_room(self):
        name = self.room_input.strip()
        if not protocol.is_valid_room_name(name):
            self.context.set_status(
                f"Room name must be {protocol.ROOM_NAME_MIN_LEN}-{protocol.ROOM_NAME_MAX_LEN} valid characters.",
                duration=3.0,
            )
            return
        self.context.room_name = name
        if not self.context.start_local_server(name):
            self.context.set_status("Could not start server (port in use or server exited).", duration=4.0)
            return
        net = nw.Network()
        result = net.connect_to_room(
            self.context.server_host,
            self.context.server_port,
            self.context.player_name,
        )
        if not result.ok:
            self.context.stop_server()
            self.context.set_status("Failed to connect to local server.", duration=3.0)
            net.close()
            return
        self.context.attach_network(net, is_host=True, room_name=result.room_name, start_pos=result.start_pos)
        self._session_open = True

    def _perform_close_room(self) -> None:
        if self.context.network:
            self.context.network.close_room()
            self.context.wait_for_server_exit(timeout=0.75)
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
        my_id = self.context.network.id if self.context.network else -1
        for event in self.context.drain_network_events():
            if self.handle_common_network_event(event):
                continue
            if self._room_ui.handle_avatar_event(event, my_id):
                continue
            if isinstance(event, nw.RosterEvent):
                entries = list(event.entries)
                old_ids = {player_id for player_id, _ready, _name in self.context.roster}
                new_ids = {player_id for player_id, _ready, _name in entries}
                if new_ids - old_ids:
                    self._room_ui.restart_avatar_broadcast()
                self.context.roster = entries
                self._room_ui.retain_remote_avatars(new_ids)
            elif isinstance(event, nw.CountdownEvent):
                self.context.countdown_remaining = event.seconds_until_start
            elif isinstance(event, nw.CountdownCancelEvent):
                self.context.countdown_remaining = None
            elif isinstance(event, nw.RoomNameEvent):
                self.context.room_name = event.room_name
            elif isinstance(event, nw.GameStartEvent):
                self.context.countdown_remaining = None
                self.switch("in_game")
                return
            elif isinstance(event, nw.GameEndEvent):
                self.context.reset_lobby_after_game()
                self.context.results_standings = list(event.standings)
                self.context.return_state_after_results = "host_lobby"
                self.switch("results")
                return

    def handle_event(self, event):
        super().handle_event(event)
        if self._room_name_edit_open:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._close_room_name_edit()
                elif event.key == pygame.K_RETURN:
                    if self._room_name_edit_save_enabled():
                        self._save_room_name_edit()
                elif not self._room_name_edit_field_active:
                    pass
                elif event.key == pygame.K_BACKSPACE:
                    if event_has_ctrl_modifier(event):
                        self._room_name_edit_value = remove_previous_input_token(
                            self._room_name_edit_value,
                            separators=" _-",
                        )
                    else:
                        self._room_name_edit_value = self._room_name_edit_value[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self._room_name_edit_value = filter_room_name_input(self._room_name_edit_value + event.unicode)
                return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                action = self._room_ui.room_name_edit_hit_test(event.pos)
                if action == "cancel":
                    self._close_room_name_edit()
                    return
                if action == "save":
                    self._save_room_name_edit()
                    return
                if action == "field":
                    self._room_name_edit_field_active = True
                    return
                if action == "frame":
                    self._room_name_edit_field_active = False
                    return
                return

        if self._confirm_close_room:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                action = self._room_ui.close_confirmation_hit_test(event.pos)
                if action == "close":
                    self._perform_close_room()
                elif action == "cancel":
                    self._cancel_dialog()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._cancel_dialog()
            return

        if not self._session_open:
            self._layout_setup()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.room_active = self.room_rect.collidepoint(event.pos)
                if self.open_button.enabled and self.open_button.rect.collidepoint(event.pos):
                    self._open_room()
            if event.type == pygame.KEYDOWN and self.room_active:
                if event.key == pygame.K_ESCAPE:
                    self.room_active = False
                elif event.key == pygame.K_RETURN:
                    if self.open_button.enabled:
                        self._open_room()
                elif event.key == pygame.K_BACKSPACE:
                    if event_has_ctrl_modifier(event):
                        self.room_input = remove_previous_input_token(self.room_input, separators=" _-")
                    else:
                        self.room_input = self.room_input[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self.room_input = filter_room_name_input(self.room_input + event.unicode)
            return

        self._layout_session()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.context.countdown_remaining is not None:
                if self.context.network:
                    self.context.network.cancel_countdown()
            else:
                self._confirm_close_room = True
                self._confirm_hovered = None
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hid = _host_player_id(self.context.roster)
            action = self._room_ui.hit_test(
                event.pos,
                self.context.roster,
                host_id=hid,
                host_view=True,
                kick_mode=self._kick_mode_on,
            )
            in_cd = self.context.countdown_remaining is not None
            if in_cd:
                if action == "primary":
                    self.context.network.cancel_countdown()
                return

            if self._room_ui.room_name_hit_test(event.pos, self.context.room_name, host_view=True):
                self._open_room_name_edit()
                return

            if action == "secondary":
                self._confirm_close_room = True
                self._confirm_hovered = None
                return

            if action == "primary":
                if self.host_and_non_host_ready():
                    self.context.network.send_start()
                else:
                    self.context.set_status(self._start_disable_reason(), duration=2.0)
                return

            if action == "kick_toggle":
                self._kick_mode_on = not self._kick_mode_on
                return

            if isinstance(action, tuple) and action[0] == "kick":
                _kind, target_id, _name = action
                if self.context.network:
                    self.context.network.send_kick(target_id)
                return

    def update(self, dt: float):
        self._pulse_t += dt
        mp = self.context.mouse_pos
        if self._room_name_edit_open:
            self._room_name_edit_hovered = self._room_ui.room_name_edit_hit_test(mp)
            return
        if self._confirm_close_room:
            self._confirm_hovered = self._room_ui.close_confirmation_hit_test(mp)
            return
        if self._session_open:
            self._drain_network()
            in_cd = self.context.countdown_remaining is not None
            self.start_button.enabled = (not in_cd) and self.host_and_non_host_ready()
            self.cancel_button.enabled = in_cd
            self.close_button.enabled = True
            self._room_ui.update(dt, self.context.network)
            self._layout_session()
            action = self._room_ui.hit_test(
                mp,
                self.context.roster,
                host_id=_host_player_id(self.context.roster),
                host_view=True,
                kick_mode=self._kick_mode_on,
            )
            if in_cd and action != "primary":
                action = None
            if action is None and not in_cd and self._room_ui.room_name_hit_test(mp, self.context.room_name, host_view=True):
                action = "room_name"
            self._hovered = ("kick", action[1]) if isinstance(action, tuple) and action[0] == "kick" else action
        else:
            self._layout_setup()
            self.open_button.enabled = protocol.is_valid_room_name(self.room_input)
            self._open_h = self.open_button.rect.collidepoint(mp)

    def draw(self, surface):
        theme = DEFAULT_THEME

        if not self._session_open:
            super().draw(surface)
            self._layout_setup()
            title = self.context.title_font.render("Host a room", True, theme.text)
            surface.blit(title, title.get_rect(center=(surface.get_width() // 2, 76)))

            inp = ui.TextInput(
                self.room_rect,
                f"Room name ({protocol.ROOM_NAME_MIN_LEN}-{protocol.ROOM_NAME_MAX_LEN} chars)",
                self.room_input,
                self.room_active,
            )
            ui.draw_text_input(surface, (self.context.font, self.context.tiny_font), inp, theme)

            if not protocol.is_valid_room_name(self.room_input):
                warn = self.context.tiny_font.render(
                    f"Room name must be {protocol.ROOM_NAME_MIN_LEN}-{protocol.ROOM_NAME_MAX_LEN} chars; no edge symbols.",
                    True,
                    theme.text_warn,
                )
                surface.blit(warn, (self.room_rect.x, self.room_rect.y + self.room_rect.height + 8))

            ui.draw_button(surface, self.context.small_font, self.open_button, theme, hovered=self._open_h)
            return

        hid = _host_player_id(self.context.roster)
        primary_enabled = self.context.countdown_remaining is not None or self.host_and_non_host_ready()
        self._room_ui.draw_base(
            surface,
            self.context.roster,
            host_id=hid,
            host_view=True,
            kick_mode=self._kick_mode_on,
            hovered=self._hovered,
            primary_enabled=primary_enabled,
        )

        if self._confirm_close_room:
            self._room_ui.draw_close_confirmation_base(surface, self._confirm_hovered)
        if self._room_name_edit_open:
            self._room_ui.draw_room_name_edit_base(
                surface,
                self._room_name_edit_save_enabled(),
                self._room_name_edit_field_active,
                self._room_name_edit_hovered,
            )

    def draw_window_overlay(self, surface: pygame.Surface):
        if not self._session_open:
            return
        if self._confirm_close_room:
            self._room_ui.draw_close_confirmation_window_overlay(surface)
            return
        if self._room_name_edit_open:
            self._room_ui.draw_room_name_edit_window_overlay(
                surface,
                self._room_name_edit_value,
                self._room_name_edit_save_enabled(),
                self._room_name_edit_field_active,
            )
            return
        network = self.context.network
        local_id = network.id if network is not None else None
        in_cd = self.context.countdown_remaining is not None
        primary_enabled = in_cd or self.host_and_non_host_ready()
        self._room_ui.draw_window_overlay(
            surface,
            self.context.roster,
            room_name=self.context.room_name,
            host_id=_host_player_id(self.context.roster),
            local_player_id=local_id,
            host_view=True,
            kick_mode=self._kick_mode_on,
            primary_enabled=primary_enabled,
            primary_label="CANCEL" if in_cd else "START",
            secondary_label="CLOSE ROOM",
            countdown_remaining=self.context.countdown_remaining,
            pulse_t=self._pulse_t,
            room_name_hovered=self._hovered == "room_name",
        )
