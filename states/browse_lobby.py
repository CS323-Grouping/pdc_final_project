import ipaddress
import time

import pygame

from network.discovery import LobbyBrowser
from network import network_handler as nw
from network import protocol
from states.common import ScreenState, event_has_ctrl_modifier, filter_room_name_input, remove_previous_input_token
from ui import animations as anim
from ui.theme import DEFAULT_THEME


BROWSER_RECTS = {
    "background": pygame.Rect(0, 0, 320, 180),
    "title": pygame.Rect(10, 14, 300, 16),
    "left_section": pygame.Rect(10, 32, 92, 134),
    "right_section": pygame.Rect(110, 32, 200, 134),
    "back": pygame.Rect(17, 40, 22, 18),
    "refresh": pygame.Rect(44, 40, 53, 18),
    "player_name": pygame.Rect(17, 60, 78, 16),
    "create": pygame.Rect(17, 78, 78, 24),
    "join": pygame.Rect(17, 106, 78, 24),
    "direct_join": pygame.Rect(17, 134, 78, 24),
    "search": pygame.Rect(117, 42, 186, 18),
    "search_icon": pygame.Rect(124, 46, 9, 10),
    "room_card": pygame.Rect(117, 66, 186, 30),
}


class BrowseLobbyState(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.browser: LobbyBrowser | None = None
        self.room_rows: list = []
        self._rooms = []
        self._card_seen: dict[tuple[str, int], float] = {}
        self._selected_room_key: tuple[str, int] | None = None
        self._hovered: str | None = None
        self._search_active = False
        self._search_text = ""
        self._assets: dict[str, pygame.Surface] = {}
        self._window_fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        # Direct join overlay state
        self._direct_join_active = False
        self._direct_join_field: str | None = None
        self._direct_join_ip = ""
        self._direct_join_port = ""
        # Create room overlay state
        self._create_room_active = False
        self._create_room_field_active = False
        self._create_room_name = ""

    def enter(self):
        self._assets = self._load_assets()
        self.browser = LobbyBrowser(discovery_port=self.context.discovery_port)
        self.browser.start()
        self._card_seen.clear()
        self.context.set_status("Searching for LAN rooms...", duration=2.0)

    def exit(self):
        if self.browser is not None:
            self.browser.stop()
            self.browser = None

    def _load_assets(self) -> dict[str, pygame.Surface]:
        root = self.context.project_root / "assets" / "roomBrowser"
        menu_root = self.context.project_root / "assets" / "Menu"
        names = {
            "background": menu_root / "MenuBackground_Image.png",
            "left_section": root / "RoomBrowserLeftSection_Frame.png",
            "right_section": root / "RoomBrowserRightSection_Frame.png",
            "back": root / "RoomBrowserBack_Button.png",
            "refresh": root / "RoomBrowserRefresh_Button.png",
            "button": root / "RoomBrowserJoinCreateDirect_Button.png",
            "search": root / "RoomBrowserSearchBar_Frame.png",
            "search_icon": root / "RoomBrowserSearchBar_Icon.png",
            "room_card": root / "RoomBrowserList_Frame.png",
            "user_icon": root / "RoomBrowserUser_Icon.png",
            "create_room_frame": root / "CreateRoomWindow_Frame.png",
            "create_room_field": root / "CreateRoomWindowRoomName_Field.png",
            "create_room_create": root / "CreateRoomWindowCreate_Button.png",
            "create_room_create_disabled": root / "CreateRoomWindowCreate_ButtonDisabled.png",
            "create_room_cancel": root / "CreateRoomWindowCancel_Button.png",
            "direct_join_frame": root / "DirectJoinWindow_Frame.png",
            "direct_join_address": root / "DirectJoinWindowAddress_Field.png",
            "direct_join_port": root / "DirectJoinWindowPort_Field.png",
            "direct_join_join": root / "DirectJoinWindowJoin_Button.png",
            "direct_join_join_disabled": root / "DirectJoinWindowJoin_ButtonDisabled.png",
            "direct_join_cancel": root / "DirectJoinWindowCancel_Button.png",
        }
        assets: dict[str, pygame.Surface] = {}
        for key, path in names.items():
            try:
                assets[key] = pygame.image.load(str(path)).convert_alpha()
            except (FileNotFoundError, pygame.error):
                rect = BROWSER_RECTS.get(key, pygame.Rect(0, 0, 16, 16))
                fallback = pygame.Surface((max(1, rect.w), max(1, rect.h)), pygame.SRCALPHA)
                fallback.fill((26, 39, 58, 255))
                assets[key] = fallback
        disabled = self._load_optional_asset(
            root,
            (
                "RoomBrowserJoinCreateDirect_ButtonDisabled.png",
                "RoomBrowserJoinCreate_Button_Disabled.png",
                "RoomBrowserJoinCreate_ButtonDisabled.png",
                "RoomBrowserJoinCreate_DisabledButton.png",
                "RoomBrowserJoinDisabled_Button.png",
                "RoomBrowserJoin_Button_Disabled.png",
            ),
        )
        assets["button_disabled"] = disabled if disabled is not None else self._make_disabled_button(assets["button"])
        return assets

    def _load_optional_asset(self, root, filenames: tuple[str, ...]) -> pygame.Surface | None:
        for filename in filenames:
            path = root / filename
            if not path.exists():
                continue
            try:
                return pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                continue
        return None

    def _make_disabled_button(self, source: pygame.Surface) -> pygame.Surface:
        disabled = source.copy()
        shade = pygame.Surface(disabled.get_size(), pygame.SRCALPHA)
        shade.fill((10, 16, 28, 150))
        disabled.blit(shade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return disabled

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

    def _status_label(self, room, reconnectable: bool = False) -> str:
        if reconnectable:
            return "RECONNECT"
        if room.state == protocol.STATE_PAUSED:
            return "PAUSED"
        if room.state == protocol.STATE_COUNTDOWN:
            return "STARTING"
        if room.state == protocol.STATE_IN_GAME:
            return "IN GAME"
        if room.current_players >= room.max_players:
            return "FULL"
        return "LOBBY"

    def _status_color(self, room, reconnectable: bool = False) -> tuple[int, int, int]:
        if reconnectable:
            return (120, 190, 255)
        if room.state in (protocol.STATE_IN_GAME, protocol.STATE_PAUSED):
            return (230, 130, 105)
        if room.state == protocol.STATE_COUNTDOWN:
            return (245, 205, 95)
        if room.current_players >= room.max_players:
            return (180, 180, 190)
        return (115, 225, 150)

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
            result = net.reconnect_to_room(room.addr, room.game_port, -1, 0, self.context.player_name)
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

    def _direct_join_room_by_addr(self, addr: str, port: int):
        """Attempt a direct join to the given IP address and port."""
        net = nw.Network()
        result = net.connect_to_room(addr, port, self.context.player_name)
        if not result.ok:
            if result.reason_code == protocol.CONNO_REASON_COOLDOWN:
                if result.extra == protocol.UINT32_MAX:
                    self.context.set_banner("On cooldown - rejoin blocked for this session.", duration=6.0)
                else:
                    self.context.set_banner(f"On cooldown - {result.extra} seconds remaining.", duration=6.0)
                net.close()
                self.switch("menu")
                return
            if result.reason_code == protocol.CONNO_REASON_IN_GAME:
                self.context.set_status("Room is no longer joinable.", duration=3.0)
            elif result.reason_code == protocol.CONNO_REASON_FULL:
                self.context.set_status("Room is already full.", duration=3.0)
            elif result.reason_code == protocol.CONNO_REASON_NAME_TAKEN:
                self.context.set_status("Player name is already in this room.", duration=3.0)
            else:
                self.context.set_status("Failed to connect to host.", duration=3.0)
            net.close()
            return
        self.context.attach_network(
            network_obj=net,
            is_host=False,
            room_name=result.room_name,
            start_pos=result.start_pos,
        )
        self.switch("joined_lobby")

    def _submit_direct_join(self):
        """Validate and attempt the direct join IP/port entered by the user."""
        addr = self._direct_join_ip.strip()
        port_str = self._direct_join_port.strip()
        if not self._direct_join_address_valid():
            self.context.set_status("Enter a valid IPv4 address.", duration=2.0)
            return
        if not self._direct_join_port_valid():
            self.context.set_status("Enter a valid port (1-65535).", duration=2.0)
            return
        self._direct_join_active = False
        self._direct_join_field = None
        self._direct_join_room_by_addr(addr, int(port_str))

    def _join_room(self, room):
        net = nw.Network()
        result = net.connect_to_room(room.addr, room.game_port, self.context.player_name)
        if not result.ok:
            if result.reason_code == protocol.CONNO_REASON_COOLDOWN:
                if result.extra == protocol.UINT32_MAX:
                    self.context.set_banner("On cooldown - rejoin blocked for this session.", duration=6.0)
                else:
                    self.context.set_banner(f"On cooldown - {result.extra} seconds remaining.", duration=6.0)
                net.close()
                self.switch("menu")
                return
            if result.reason_code == protocol.CONNO_REASON_IN_GAME:
                self.context.set_status("Room is no longer joinable.", duration=3.0)
            elif result.reason_code == protocol.CONNO_REASON_FULL:
                self.context.set_status("Room is already full.", duration=3.0)
            elif result.reason_code == protocol.CONNO_REASON_NAME_TAKEN:
                self.context.set_status("Player name is already in this room.", duration=3.0)
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

    def _create_room_layout(self) -> dict[str, pygame.Rect]:
        frame_asset = self._assets.get("create_room_frame")
        field_asset = self._assets.get("create_room_field")
        button_asset = self._assets.get("create_room_create")
        frame_w, frame_h = frame_asset.get_size() if frame_asset is not None else (148, 84)
        field_w, field_h = field_asset.get_size() if field_asset is not None else (134, 18)
        button_w, button_h = button_asset.get_size() if button_asset is not None else (64, 24)
        frame = pygame.Rect((320 - frame_w) // 2, (180 - frame_h) // 2, frame_w, frame_h)
        title = pygame.Rect(frame.x + 7, frame.y + 7, frame.w - 14, 16)
        field = pygame.Rect(frame.centerx - field_w // 2, title.bottom + 2, field_w, field_h)
        button_y = field.bottom + 8
        button_gap = 8
        total_button_w = button_w * 2 + button_gap
        create = pygame.Rect(frame.centerx - total_button_w // 2, button_y, button_w, button_h)
        cancel = pygame.Rect(create.right + button_gap, button_y, button_w, button_h)
        text = pygame.Rect(field.x + 7, field.y + 2, field.w - 14, field.h - 4)
        return {
            "frame": frame,
            "title": title,
            "field": field,
            "text": text,
            "create": create,
            "cancel": cancel,
        }

    def _direct_join_layout(self) -> dict[str, pygame.Rect]:
        frame_asset = self._assets.get("direct_join_frame")
        address_asset = self._assets.get("direct_join_address")
        port_asset = self._assets.get("direct_join_port")
        button_asset = self._assets.get("direct_join_join")
        frame_w, frame_h = frame_asset.get_size() if frame_asset is not None else (148, 84)
        address_w, address_h = address_asset.get_size() if address_asset is not None else (84, 18)
        port_w, port_h = port_asset.get_size() if port_asset is not None else (48, 18)
        button_w, button_h = button_asset.get_size() if button_asset is not None else (64, 24)
        frame = pygame.Rect((320 - frame_w) // 2, (180 - frame_h) // 2, frame_w, frame_h)
        title = pygame.Rect(frame.x + 7, frame.y + 7, frame.w - 14, 16)
        field_gap = 2
        field_y = title.bottom + 2
        total_field_w = address_w + field_gap + port_w
        address = pygame.Rect(frame.centerx - total_field_w // 2, field_y, address_w, address_h)
        port = pygame.Rect(address.right + field_gap, field_y, port_w, port_h)
        button_y = max(address.bottom, port.bottom) + 8
        button_gap = 8
        total_button_w = button_w * 2 + button_gap
        join = pygame.Rect(frame.centerx - total_button_w // 2, button_y, button_w, button_h)
        cancel = pygame.Rect(join.right + button_gap, button_y, button_w, button_h)
        return {
            "frame": frame,
            "title": title,
            "address": address,
            "address_text": pygame.Rect(address.x + 7, address.y + 2, address.w - 14, address.h - 4),
            "port": port,
            "port_text": pygame.Rect(port.x + 7, port.y + 2, port.w - 14, port.h - 4),
            "join": join,
            "cancel": cancel,
        }

    def _create_room_name_valid(self) -> bool:
        name = self._create_room_name.strip()
        return protocol.is_valid_room_name(name)

    def _direct_join_address_valid(self) -> bool:
        try:
            return ipaddress.ip_address(self._direct_join_ip.strip()).version == 4
        except ValueError:
            return False

    def _direct_join_port_valid(self) -> bool:
        port = self._direct_join_port.strip()
        return port.isdigit() and 1 <= int(port) <= 65535

    def _direct_join_valid(self) -> bool:
        return self._direct_join_address_valid() and self._direct_join_port_valid()

    def _open_create_room_window(self):
        self._create_room_active = True
        self._create_room_field_active = False
        self._create_room_name = ""
        self._search_active = False
        self._direct_join_active = False
        self._direct_join_field = None

    def _open_direct_join_window(self):
        self._direct_join_active = True
        self._direct_join_field = None
        self._direct_join_ip = ""
        self._direct_join_port = ""
        self._create_room_active = False
        self._create_room_field_active = False
        self._search_active = False

    def _submit_create_room(self):
        name = self._create_room_name.strip()
        if not self._create_room_name_valid():
            self.context.set_status(
                f"Room name must be {protocol.ROOM_NAME_MIN_LEN}-{protocol.ROOM_NAME_MAX_LEN} valid characters.",
                duration=3.0,
            )
            return
        self._create_room_active = False
        self._create_room_field_active = False
        self._host_room(name)

    def _host_room(self, room_name: str):
        if not protocol.is_valid_player_name(self.context.player_name):
            self.context.set_status(
                f"Name must be {protocol.PLAYER_NAME_MIN_LEN}-{protocol.PLAYER_NAME_MAX_LEN} chars: letters, numbers, _ or -.",
                duration=3.0,
            )
            return
        if not protocol.is_valid_room_name(room_name):
            self.context.set_status(
                f"Room name must be {protocol.ROOM_NAME_MIN_LEN}-{protocol.ROOM_NAME_MAX_LEN} valid characters.",
                duration=3.0,
            )
            return
        self.context.room_name = room_name
        if not self.context.start_local_server(room_name):
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

    def _filtered_rooms(self):
        query = self._search_text.strip().lower()
        if not query:
            return list(self._rooms)
        return [room for room in self._rooms if query in room.room_name.lower() or query in room.addr.lower()]

    def handle_event(self, event):
        super().handle_event(event)
        if event.type == pygame.KEYDOWN:
            if self._create_room_active:
                if event.key == pygame.K_ESCAPE:
                    if self._create_room_field_active:
                        self._create_room_field_active = False
                    else:
                        self._create_room_active = False
                elif event.key == pygame.K_RETURN:
                    self._submit_create_room()
                elif not self._create_room_field_active:
                    pass
                elif event.key == pygame.K_BACKSPACE:
                    if event_has_ctrl_modifier(event):
                        self._create_room_name = remove_previous_input_token(self._create_room_name, separators=" _-")
                    else:
                        self._create_room_name = self._create_room_name[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self._create_room_name = filter_room_name_input(self._create_room_name + event.unicode)
                return

            if self._direct_join_active:
                if event.key == pygame.K_ESCAPE:
                    if self._direct_join_field is not None:
                        self._direct_join_field = None
                    else:
                        self._direct_join_active = False
                elif event.key == pygame.K_TAB:
                    self._direct_join_field = "port" if self._direct_join_field == "address" else "address"
                elif event.key == pygame.K_RETURN:
                    self._submit_direct_join()
                elif self._direct_join_field is None:
                    pass
                elif event.key == pygame.K_BACKSPACE:
                    if self._direct_join_field == "address":
                        if event_has_ctrl_modifier(event):
                            self._direct_join_ip = remove_previous_input_token(self._direct_join_ip, separators=".")
                        else:
                            self._direct_join_ip = self._direct_join_ip[:-1]
                    else:
                        self._direct_join_port = "" if event_has_ctrl_modifier(event) else self._direct_join_port[:-1]
                elif event.unicode and event.unicode.isprintable():
                    if self._direct_join_field == "address":
                        if event.unicode in "0123456789.":
                            self._direct_join_ip = (self._direct_join_ip + event.unicode)[:15]
                    else:
                        if event.unicode.isdigit():
                            self._direct_join_port = (self._direct_join_port + event.unicode)[:5]
                return

            if self._search_active:
                if event.key == pygame.K_ESCAPE:
                    self._search_active = False
                elif event.key == pygame.K_BACKSPACE:
                    if event_has_ctrl_modifier(event):
                        self._search_text = remove_previous_input_token(self._search_text, separators=" _-.")
                    else:
                        self._search_text = self._search_text[:-1]
                elif event.key == pygame.K_RETURN:
                    self._search_active = False
                elif event.unicode and event.unicode.isprintable():
                    self._search_text = (self._search_text + event.unicode)[:18]
                return
            if event.key == pygame.K_ESCAPE:
                self.switch("menu")
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._create_room_active:
                layout = self._create_room_layout()
                if layout["cancel"].collidepoint(event.pos):
                    self._create_room_active = False
                    self._create_room_field_active = False
                    return
                if layout["create"].collidepoint(event.pos):
                    if self._create_room_name_valid():
                        self._submit_create_room()
                    return
                if layout["field"].collidepoint(event.pos):
                    self._create_room_field_active = True
                    return
                if layout["frame"].collidepoint(event.pos):
                    self._create_room_field_active = False
                    return
                self._create_room_active = False
                self._create_room_field_active = False
                return

            if self._direct_join_active:
                layout = self._direct_join_layout()
                if layout["cancel"].collidepoint(event.pos):
                    self._direct_join_active = False
                    self._direct_join_field = None
                    return
                if layout["join"].collidepoint(event.pos):
                    if self._direct_join_valid():
                        self._submit_direct_join()
                    return
                if layout["address"].collidepoint(event.pos):
                    self._direct_join_field = "address"
                    return
                if layout["port"].collidepoint(event.pos):
                    self._direct_join_field = "port"
                    return
                if layout["frame"].collidepoint(event.pos):
                    self._direct_join_field = None
                    return
                self._direct_join_active = False
                self._direct_join_field = None
                return

            self._search_active = BROWSER_RECTS["search"].collidepoint(event.pos)
            if BROWSER_RECTS["back"].collidepoint(event.pos):
                self.switch("menu")
                return
            if BROWSER_RECTS["refresh"].collidepoint(event.pos):
                self.context.set_status("Refreshing room list...", duration=1.0)
                return
            if BROWSER_RECTS["create"].collidepoint(event.pos):
                self._open_create_room_window()
                return
            if BROWSER_RECTS["join"].collidepoint(event.pos):
                selected = self._selected_room()
                if selected is not None and selected[1]:
                    self._join_selected_room()
                return
            if BROWSER_RECTS["direct_join"].collidepoint(event.pos):
                self._open_direct_join_window()
                return
            for rect, room, _joinable, _reconnectable in self.room_rows:
                if rect.collidepoint(event.pos):
                    self._selected_room_key = (room.addr, room.game_port)
                    return

    def update(self, dt: float):
        _ = dt
        self.room_rows = []
        if self.browser is None:
            return

        now = time.monotonic()
        self._rooms = self.browser.snapshot()
        visible_rooms = self._filtered_rooms()
        alive = {(r.addr, r.game_port) for r in self._rooms}
        visible_alive = {(r.addr, r.game_port) for r in visible_rooms}
        if self._selected_room_key is not None and (
            self._selected_room_key not in alive or self._selected_room_key not in visible_alive
        ):
            self._selected_room_key = None
        for key in list(self._card_seen.keys()):
            if key not in alive:
                del self._card_seen[key]
        for room in self._rooms:
            key = (room.addr, room.game_port)
            if key not in self._card_seen:
                self._card_seen[key] = now

        y = BROWSER_RECTS["room_card"].y
        for room in visible_rooms[:3]:
            row_rect = pygame.Rect(BROWSER_RECTS["room_card"].x, y, BROWSER_RECTS["room_card"].w, BROWSER_RECTS["room_card"].h)
            reconnectable = self._can_reconnect(room)
            joinable = self._joinable(room)
            self.room_rows.append((row_rect, room, joinable, reconnectable))
            y += 34

        mp = self.context.mouse_pos
        self._hovered = None
        if self._create_room_active or self._direct_join_active:
            return
        for key in ("back", "refresh", "create", "join", "search", "direct_join"):
            if BROWSER_RECTS[key].collidepoint(mp):
                self._hovered = key
                break

    def draw(self, surface):
        background = self._assets.get("background")
        if background is not None:
            surface.blit(background, BROWSER_RECTS["background"])
        else:
            surface.fill(DEFAULT_THEME.bg)

        self._draw_asset(surface, "left_section")
        self._draw_asset(surface, "right_section")
        self._draw_asset(surface, "back")
        self._draw_asset(surface, "refresh")

        btn = self._assets["button"]
        btn_disabled = self._assets["button_disabled"]
        for key in ("create", "join", "direct_join"):
            rect = BROWSER_RECTS[key]
            if key == "join":
                selected = self._selected_room()
                join_enabled = selected is not None and selected[1]
                asset = btn if join_enabled else btn_disabled
            else:
                asset = btn
            scaled = pygame.transform.scale(asset, (rect.w, rect.h))
            surface.blit(scaled, rect)

        selected = self._selected_room()
        join_enabled = selected is not None and selected[1]
        self._draw_asset(surface, "search")
        self._draw_asset(surface, "search_icon")

        for rect, room, _joinable, _reconnectable in self.room_rows:
            key = (room.addr, room.game_port)
            card = self._assets.get("room_card")
            if card is not None:
                fade = anim.fade_in_progress(time.monotonic() - self._card_seen.get(key, time.monotonic()), 0.25)
                if fade >= 0.99:
                    surface.blit(card, rect)
                else:
                    copy = card.copy()
                    copy.set_alpha(int(255 * fade))
                    surface.blit(copy, rect)
            if self._selected_room_key == key:
                pygame.draw.rect(surface, (115, 190, 255), rect.inflate(2, 2), width=1, border_radius=2)

        if self._hovered in ("back", "refresh", "create", "join", "direct_join"):
            if self._hovered != "join" or join_enabled:
                pygame.draw.rect(surface, (115, 190, 255), BROWSER_RECTS[self._hovered].inflate(2, 2), width=1, border_radius=2)
        if self._search_active:
            pygame.draw.rect(surface, (115, 190, 255), BROWSER_RECTS["search"].inflate(1, 1), width=1, border_radius=2)

    def _draw_asset(self, surface: pygame.Surface, key: str):
        asset = self._assets.get(key)
        rect = BROWSER_RECTS[key]
        if asset is not None:
            surface.blit(asset, rect)

    def _window_scale(self) -> int:
        if self.context.display_manager is None:
            return 1
        return self.context.display_manager.config.selected_scale

    def _scale_rect(self, rect: pygame.Rect) -> pygame.Rect:
        scale = self._window_scale()
        return pygame.Rect(rect.x * scale, rect.y * scale, rect.w * scale, rect.h * scale)

    def _window_font(self, logical_size: int, bold: bool = True) -> pygame.font.Font:
        scale = self._window_scale()
        size = max(10, logical_size * scale)
        key = (size, bold)
        font = self._window_fonts.get(key)
        if font is None:
            font = pygame.font.SysFont("consolas", size, bold=bold)
            self._window_fonts[key] = font
        return font

    def _fit_text(self, text: str, font: pygame.font.Font, max_width: int) -> str:
        if font.size(text)[0] <= max_width:
            return text
        out = text
        while out and font.size(out + ".")[0] > max_width:
            out = out[:-1]
        return (out + ".") if out else "."

    def _draw_text_center(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        bold: bool = True,
        shadow: bool = True,
    ):
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size, bold=bold)
        text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        if shadow:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, shade.get_rect(center=(rect.centerx + scale, rect.centery + scale)))
        label = font.render(text, True, color)
        surface.blit(label, label.get_rect(center=rect.center))

    def _draw_text_left(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        bold: bool = True,
        shadow: bool = False,
    ):
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size, bold=bold)
        text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        y = rect.y + (rect.h - font.get_height()) // 2
        if shadow:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, (rect.x + scale, y + scale))
        label = font.render(text, True, color)
        surface.blit(label, (rect.x, y))

    def _draw_text_caret(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        bold: bool = True,
    ):
        if int(time.monotonic() * 2) % 2 != 0:
            return
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size, bold=bold)
        fitted_text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        text_width = font.size(fitted_text)[0] if fitted_text else 0
        caret_w = max(1, scale)
        caret_h = max(caret_w, font.get_height() - (2 * scale))
        x = min(rect.right - caret_w, rect.x + text_width + scale)
        y = rect.y + (rect.h - caret_h) // 2
        pygame.draw.rect(surface, color, pygame.Rect(x, y, caret_w, caret_h))

    def draw_window_overlay(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        self._draw_text_center(surface, 9, "ROOM BROWSER", BROWSER_RECTS["title"], (180, 220, 255))
        self._draw_text_center(surface, 6, "REFRESH", BROWSER_RECTS["refresh"], (215, 235, 250))
        self._draw_text_center(surface, 7, self.context.player_name, BROWSER_RECTS["player_name"], (190, 220, 255))
        self._draw_text_center(surface, 7, "CREATE", BROWSER_RECTS["create"], theme.text)
        selected = self._selected_room()
        join_color = theme.text if selected is not None and selected[1] else theme.text_muted
        self._draw_text_center(surface, 7, "JOIN", BROWSER_RECTS["join"], join_color)
        self._draw_text_center(surface, 7, "DIRECT JOIN", BROWSER_RECTS["direct_join"], theme.text)

        if self._search_text:
            search_text = self._search_text
            search_color = theme.text
        elif self._search_active:
            search_text = ""
            search_color = theme.text
        else:
            search_text = "SEARCH"
            search_color = theme.text_muted
        search_text_rect = pygame.Rect(137, BROWSER_RECTS["search"].y + 2, 158, 14)
        self._draw_text_left(
            surface,
            7,
            search_text,
            search_text_rect,
            search_color,
        )
        if self._search_active:
            self._draw_text_caret(surface, 7, self._search_text, search_text_rect, theme.text)

        for rect, room, joinable, reconnectable in self.room_rows:
            self._draw_room_row_text(surface, rect, room, joinable, reconnectable)
        self._draw_window_global_messages(surface)

        if self._create_room_active:
            self._draw_create_room_overlay(surface)
        if self._direct_join_active:
            self._draw_direct_join_overlay(surface)

    def _draw_window_asset(self, surface: pygame.Surface, key: str, logical_rect: pygame.Rect):
        asset = self._assets.get(key)
        if asset is None:
            return
        rect = self._scale_rect(logical_rect)
        surface.blit(pygame.transform.scale(asset, rect.size), rect)

    def _draw_window_hover_outline(self, surface: pygame.Surface, logical_rect: pygame.Rect):
        scale = self._window_scale()
        rect = self._scale_rect(logical_rect.inflate(2, 2))
        pygame.draw.rect(surface, (115, 190, 255), rect, width=max(1, scale), border_radius=2 * scale)

    def _draw_create_room_overlay(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        layout = self._create_room_layout()
        create_enabled = self._create_room_name_valid()
        self._draw_window_asset(surface, "create_room_frame", layout["frame"])
        self._draw_window_asset(surface, "create_room_field", layout["field"])
        create_asset = "create_room_create" if create_enabled else "create_room_create_disabled"
        self._draw_window_asset(surface, create_asset, layout["create"])
        self._draw_window_asset(surface, "create_room_cancel", layout["cancel"])

        mouse_pos = self.context.mouse_pos
        if self._create_room_field_active:
            self._draw_window_hover_outline(surface, layout["field"])
        if create_enabled and layout["create"].collidepoint(mouse_pos):
            self._draw_window_hover_outline(surface, layout["create"])
        if layout["cancel"].collidepoint(mouse_pos):
            self._draw_window_hover_outline(surface, layout["cancel"])

        self._draw_text_center(surface, 7, "CREATE ROOM", layout["title"], (180, 220, 255))
        if self._create_room_name:
            name_text = self._create_room_name
            name_color = theme.text
        elif self._create_room_field_active:
            name_text = ""
            name_color = theme.text
        else:
            name_text = "ROOM NAME"
            name_color = theme.text_muted
        self._draw_text_left(surface, 7, name_text, layout["text"], name_color, shadow=False)
        if self._create_room_field_active:
            self._draw_text_caret(surface, 7, self._create_room_name, layout["text"], theme.text)
        create_color = theme.text if create_enabled else theme.text_muted
        self._draw_text_center(surface, 7, "CREATE", layout["create"], create_color)
        self._draw_text_center(surface, 7, "CANCEL", layout["cancel"], theme.text)

    def _draw_direct_join_overlay(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        layout = self._direct_join_layout()
        join_enabled = self._direct_join_valid()
        self._draw_window_asset(surface, "direct_join_frame", layout["frame"])
        self._draw_window_asset(surface, "direct_join_address", layout["address"])
        self._draw_window_asset(surface, "direct_join_port", layout["port"])
        join_asset = "direct_join_join" if join_enabled else "direct_join_join_disabled"
        self._draw_window_asset(surface, join_asset, layout["join"])
        self._draw_window_asset(surface, "direct_join_cancel", layout["cancel"])

        mouse_pos = self.context.mouse_pos
        if self._direct_join_field == "address":
            self._draw_window_hover_outline(surface, layout["address"])
        if self._direct_join_field == "port":
            self._draw_window_hover_outline(surface, layout["port"])
        if join_enabled and layout["join"].collidepoint(mouse_pos):
            self._draw_window_hover_outline(surface, layout["join"])
        if layout["cancel"].collidepoint(mouse_pos):
            self._draw_window_hover_outline(surface, layout["cancel"])

        self._draw_text_center(surface, 7, "DIRECT JOIN", layout["title"], (180, 220, 255))
        if self._direct_join_ip:
            address_text = self._direct_join_ip
            address_color = theme.text
        elif self._direct_join_field == "address":
            address_text = ""
            address_color = theme.text
        else:
            address_text = "IP ADDRESS"
            address_color = theme.text_muted
        if self._direct_join_port:
            port_text = self._direct_join_port
            port_color = theme.text
        elif self._direct_join_field == "port":
            port_text = ""
            port_color = theme.text
        else:
            port_text = "PORT"
            port_color = theme.text_muted
        self._draw_text_left(surface, 7, address_text, layout["address_text"], address_color, shadow=False)
        self._draw_text_left(surface, 7, port_text, layout["port_text"], port_color, shadow=False)
        if self._direct_join_field == "address":
            self._draw_text_caret(surface, 7, self._direct_join_ip, layout["address_text"], theme.text)
        if self._direct_join_field == "port":
            self._draw_text_caret(surface, 7, self._direct_join_port, layout["port_text"], theme.text)
        join_color = theme.text if join_enabled else theme.text_muted
        self._draw_text_center(surface, 7, "JOIN", layout["join"], join_color)
        self._draw_text_center(surface, 7, "CANCEL", layout["cancel"], theme.text)

    def _draw_room_row_text(self, surface: pygame.Surface, rect: pygame.Rect, room, joinable: bool, reconnectable: bool):
        theme = DEFAULT_THEME
        key = (room.addr, room.game_port)
        selected = self._selected_room_key == key
        title_color = (255, 236, 170) if selected else theme.text
        status_color = self._status_color(room, reconnectable)
        muted = theme.text_muted if joinable else (115, 120, 135)

        room_name = room.room_name[:14]
        self._draw_text_left(surface, 7, room_name, pygame.Rect(rect.x + 8, rect.y + 7, 86, 14), title_color)
        user_icon = self._assets.get("user_icon")
        if user_icon is not None:
            icon_rect = self._scale_rect(pygame.Rect(rect.x + 102, rect.y + 9, 16, 11))
            surface.blit(pygame.transform.scale(user_icon, icon_rect.size), icon_rect)
        self._draw_text_left(
            surface,
            7,
            f"{room.current_players}/{room.max_players}",
            pygame.Rect(rect.x + 122, rect.y + 7, 24, 14),
            muted,
        )

        divider = self._scale_rect(pygame.Rect(rect.x + 149, rect.y + 7, 1, 14))
        pygame.draw.rect(surface, (70, 96, 120), divider)
        self._draw_text_left(surface, 7, self._status_label(room, reconnectable), pygame.Rect(rect.x + 154, rect.y + 7, 28, 14), status_color)

    def _draw_window_global_messages(self, surface: pygame.Surface):
        scale = self._window_scale()
        if self.context.banner_message:
            rect = pygame.Rect(0, 0, surface.get_width(), 30 * scale)
            pygame.draw.rect(surface, (120, 40, 50), rect)
            font = self._window_font(7)
            label = font.render(self.context.banner_message, True, DEFAULT_THEME.text)
            surface.blit(label, (10 * scale, 5 * scale))
        if self.context.status_message:
            y = 34 * scale if self.context.banner_message else 8 * scale
            font = self._window_font(6)
            label = font.render(self.context.status_message, True, (255, 230, 120))
            surface.blit(label, (8 * scale, y))
