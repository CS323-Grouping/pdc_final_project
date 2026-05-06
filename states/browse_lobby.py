import time

import pygame

from network.discovery import LobbyBrowser
from network import network_handler as nw
from network import protocol
from states.common import ScreenState
from ui import animations as anim
from ui.theme import DEFAULT_THEME


BROWSER_RECTS = {
    "background": pygame.Rect(0, 0, 320, 180),
    "title": pygame.Rect(10, 14, 300, 16),
    "left_section": pygame.Rect(10, 32, 92, 134),
    "right_section": pygame.Rect(110, 32, 200, 134),
    "back": pygame.Rect(17, 42, 22, 18),
    "refresh": pygame.Rect(44, 42, 53, 18),
    "player_name": pygame.Rect(17, 64, 78, 14),
    "create": pygame.Rect(17, 81, 78, 22),
    "join": pygame.Rect(17, 106, 78, 22),
    "direct_connect": pygame.Rect(17, 131, 78, 22),
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
        # Direct connect overlay state
        self._direct_connect_active = False
        self._direct_connect_field = "ip"   # "ip" or "port"
        self._direct_connect_ip = ""
        self._direct_connect_port = ""

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
            "button": root / "RoomBrowserJoinCreate_Button.png",
            "search": root / "RoomBrowserSearchBar_Frame.png",
            "search_icon": root / "RoomBrowserSearchBar_Icon.png",
            "room_card": root / "RoomBrowserList_Frame.png",
            "user_icon": root / "RoomBrowserUser_Icon.png",
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

    def _join_room_by_addr(self, addr: str, port: int):
        """Attempt a direct connection to the given IP address and port."""
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

    def _submit_direct_connect(self):
        """Validate and attempt the direct IP/port connection entered by the user."""
        addr = self._direct_connect_ip.strip()
        port_str = self._direct_connect_port.strip()
        if not addr:
            self.context.set_status("Enter an IP address.", duration=2.0)
            return
        if not port_str.isdigit() or not (1 <= int(port_str) <= 65535):
            self.context.set_status("Enter a valid port (1-65535).", duration=2.0)
            return
        self._direct_connect_active = False
        self._join_room_by_addr(addr, int(port_str))

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

    def _filtered_rooms(self):
        query = self._search_text.strip().lower()
        if not query:
            return list(self._rooms)
        return [room for room in self._rooms if query in room.room_name.lower() or query in room.addr.lower()]

    def handle_event(self, event):
        super().handle_event(event)
        if event.type == pygame.KEYDOWN:
            if self._direct_connect_active:
                if event.key == pygame.K_ESCAPE:
                    self._direct_connect_active = False
                elif event.key == pygame.K_TAB:
                    # Toggle between IP and port fields
                    self._direct_connect_field = "port" if self._direct_connect_field == "ip" else "ip"
                elif event.key == pygame.K_RETURN:
                    self._submit_direct_connect()
                elif event.key == pygame.K_BACKSPACE:
                    if self._direct_connect_field == "ip":
                        self._direct_connect_ip = self._direct_connect_ip[:-1]
                    else:
                        self._direct_connect_port = self._direct_connect_port[:-1]
                elif event.unicode and event.unicode.isprintable():
                    if self._direct_connect_field == "ip":
                        # Allow digits and dots for IP addresses
                        if event.unicode in "0123456789.":
                            self._direct_connect_ip = (self._direct_connect_ip + event.unicode)[:15]
                    else:
                        if event.unicode.isdigit():
                            self._direct_connect_port = (self._direct_connect_port + event.unicode)[:5]
                return

            if event.key == pygame.K_ESCAPE:
                self.switch("menu")
                return
            if self._search_active:
                if event.key == pygame.K_BACKSPACE:
                    self._search_text = self._search_text[:-1]
                elif event.key == pygame.K_RETURN:
                    self._search_active = False
                elif event.unicode and event.unicode.isprintable():
                    self._search_text = (self._search_text + event.unicode)[:18]
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._direct_connect_active:
                overlay_rect = pygame.Rect(60, 60, 200, 60)
                if not overlay_rect.collidepoint(event.pos):
                    self._direct_connect_active = False
                return

            self._search_active = BROWSER_RECTS["search"].collidepoint(event.pos)
            if BROWSER_RECTS["back"].collidepoint(event.pos):
                self.switch("menu")
                return
            if BROWSER_RECTS["refresh"].collidepoint(event.pos):
                self.context.set_status("Refreshing room list...", duration=1.0)
                return
            if BROWSER_RECTS["create"].collidepoint(event.pos):
                self._host_room()
                return
            if BROWSER_RECTS["join"].collidepoint(event.pos):
                selected = self._selected_room()
                if selected is not None and selected[1]:
                    self._join_selected_room()
                return
            if BROWSER_RECTS["direct_connect"].collidepoint(event.pos):
                self._direct_connect_active = True
                self._direct_connect_field = "ip"
                self._direct_connect_ip = ""
                self._direct_connect_port = ""
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
        for key in ("back", "refresh", "create", "join", "search", "direct_connect"):
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
        for key in ("create", "join", "direct_connect"):
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

        if self._hovered in ("back", "refresh", "create", "join", "direct_connect"):
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

    def draw_window_overlay(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        self._draw_text_center(surface, 9, "ROOM BROWSER", BROWSER_RECTS["title"], (180, 220, 255))
        self._draw_text_center(surface, 6, "REFRESH", BROWSER_RECTS["refresh"], (215, 235, 250))
        self._draw_text_center(surface, 7, self.context.player_name, BROWSER_RECTS["player_name"], (190, 220, 255))
        self._draw_text_center(surface, 7, "CREATE", BROWSER_RECTS["create"], theme.text)
        selected = self._selected_room()
        join_color = theme.text if selected is not None and selected[1] else theme.text_muted
        self._draw_text_center(surface, 7, "JOIN", BROWSER_RECTS["join"], join_color)
        self._draw_text_center(surface, 7, "DIRECT CONNECT", BROWSER_RECTS["direct_connect"], (160, 200, 240))

        search_text = self._search_text if self._search_text else "SEARCH"
        search_color = theme.text if self._search_text else theme.text_muted
        self._draw_text_left(
            surface,
            7,
            search_text,
            pygame.Rect(137, BROWSER_RECTS["search"].y + 2, 158, 14),
            search_color,
        )

        for rect, room, joinable, reconnectable in self.room_rows:
            self._draw_room_row_text(surface, rect, room, joinable, reconnectable)
        self._draw_window_global_messages(surface)

        if self._direct_connect_active:
            self._draw_direct_connect_overlay(surface)

    def _draw_direct_connect_overlay(self, surface: pygame.Surface):
        scale = self._window_scale()
        panel = pygame.Rect(60 * scale, 60 * scale, 200 * scale, 60 * scale)
        pygame.draw.rect(surface, (18, 28, 44), panel, border_radius=4 * scale)
        pygame.draw.rect(surface, (80, 120, 170), panel, width=1 * scale, border_radius=4 * scale)

        self._draw_text_center(surface, 7, "DIRECT CONNECT", pygame.Rect(60, 62, 200, 10), (180, 220, 255))

        ip_rect = pygame.Rect(68, 74, 112, 12)
        ip_border_color = (115, 190, 255) if self._direct_connect_field == "ip" else (50, 80, 110)
        pygame.draw.rect(surface, (10, 18, 32), self._scale_rect(ip_rect))
        pygame.draw.rect(surface, ip_border_color, self._scale_rect(ip_rect), width=1 * scale)
        ip_display = self._direct_connect_ip if self._direct_connect_ip else "IP ADDRESS"
        ip_color = (215, 235, 255) if self._direct_connect_ip else (80, 110, 140)
        self._draw_text_left(surface, 6, ip_display, pygame.Rect(70, 75, 108, 10), ip_color, bold=False)

        port_rect = pygame.Rect(186, 74, 64, 12)
        port_border_color = (115, 190, 255) if self._direct_connect_field == "port" else (50, 80, 110)
        pygame.draw.rect(surface, (10, 18, 32), self._scale_rect(port_rect))
        pygame.draw.rect(surface, port_border_color, self._scale_rect(port_rect), width=1 * scale)
        port_display = self._direct_connect_port if self._direct_connect_port else "PORT"
        port_color = (215, 235, 255) if self._direct_connect_port else (80, 110, 140)
        self._draw_text_left(surface, 6, port_display, pygame.Rect(188, 75, 60, 10), port_color, bold=False)

        self._draw_text_center(surface, 5, "TAB to switch fields  |  ENTER to connect  |  ESC to cancel",
                               pygame.Rect(60, 89, 200, 8), (80, 110, 140), bold=False)

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
