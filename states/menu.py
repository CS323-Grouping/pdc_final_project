import pygame

from app.display import DisplayConfig
from network import protocol
from network.discovery import LobbyBrowser, PresenceEntry
from player_scripts.animation import load_spritesheet_frames
from player_scripts.avatar_sprite import AVATAR_RECT, crop_square
from states.common import ScreenState, event_has_ctrl_modifier, filter_player_name_input, remove_previous_input_token
from ui.theme import DEFAULT_THEME
from world.constants import PLAYER_FRAME_HEIGHT, PLAYER_FRAME_WIDTH


RESOLUTION_LABELS = {
    2: "640x360",
    3: "960x540",
    4: "1280x720",
    5: "1600x900",
    6: "1920x1080",
}


MENU_ASSET_RECTS = {
    "background": pygame.Rect(0, 0, 320, 180),
    "avatar_section": pygame.Rect(10, 40, 68, 100),
    "avatar_bg": pygame.Rect(21, 62, 46, 46),
    "avatar_frame": pygame.Rect(19, 60, 50, 50),
    "avatar_model": pygame.Rect(33, 65, 22, 32),
    "avatar_platform": pygame.Rect(24, 97, 40, 8),
    "avatar_button": pygame.Rect(17, 115, 54, 18),
    "crown": pygame.Rect(145, 10, 30, 22),
    "title": pygame.Rect(88, 33, 144, 62),
    "play": pygame.Rect(99, 100, 122, 26),
    "exit": pygame.Rect(99, 130, 92, 26),
    "settings": pygame.Rect(195, 130, 26, 26),
    "online_section": pygame.Rect(242, 14, 68, 152),
}

ONLINE_CARD_RECTS = (
    pygame.Rect(249, 39, 54, 24),
    pygame.Rect(249, 68, 54, 24),
    pygame.Rect(249, 97, 54, 24),
    pygame.Rect(249, 126, 54, 24),
)

NAME_DISPLAY_RECT = pygame.Rect(14, 48, 60, 10)


class MainMenuState(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.name_input = context.player_name
        self._name_edit_open = False
        self._name_edit_field_active = False
        self._name_edit_original = context.player_name
        self._name_edit_value = context.player_name
        self._settings_open = False
        self._pending_scale = context.display_manager.config.selected_scale if context.display_manager else 4
        self._pending_fullscreen = context.display_manager.config.fullscreen if context.display_manager else False
        self._resolution_rects: list[tuple[pygame.Rect, int]] = []
        self._settings_dropdown_open = False
        self._presence_entries: list[PresenceEntry] = []
        self._hovered: str | None = None
        self._browser: LobbyBrowser | None = None
        self._assets: dict[str, pygame.Surface] = {}
        self._menu_font = pygame.font.SysFont("consolas", 8, bold=True)
        self._menu_font_sm = pygame.font.SysFont("consolas", 7, bold=True)
        self._menu_font_lg = pygame.font.SysFont("consolas", 13, bold=True)
        self._window_fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self._idle_body_frame: pygame.Surface | None = None

    def enter(self):
        self.context.detach_network(send_disconnect=False)
        self.context.stop_server()
        self._assets = self._load_assets()
        self._load_player_preview_frame()
        self._start_browser()

    def exit(self):
        self._stop_browser()

    def _load_assets(self) -> dict[str, pygame.Surface]:
        root = self.context.project_root / "assets" / "Menu"
        names = {
            "background": "MenuBackground_Image.png",
            "avatar_section": "AvatarSection_Frame.png",
            "avatar_bg": "AvatarDisplay_Background.png",
            "avatar_frame": "AvatarDisplay_Frame.png",
            "avatar_model": "AvatarDisplay_Model.png",
            "avatar_platform": "AvatarDisplay_Platform.png",
            "avatar_button": "AvatarSection_Button.png",
            "crown": "MenuBanner_Crown.png",
            "title": "MenuBanner_Title.png",
            "play": "MenuPlay_Button.png",
            "exit": "MenuExit_Button.png",
            "settings": "MenuSettings_Button.png",
            "online_section": "OnlineSection_Frame.png",
            "online_card": "OnlineSection_Card.png",
            "name_edit_frame": "NameEditWindow_Frame.png",
            "name_edit_field": "NameEditWindowNameField_Frame.png",
            "name_edit_save": "NameEditWindowSave_Button.png",
            "name_edit_save_disabled": "NameEditWindowSave_ButtonDisabled.png",
            "name_edit_cancel": "NameEditWindowCancel_Button.png",
        }
        fallbacks = {
            "name_edit_frame": (148, 84),
            "name_edit_field": (134, 18),
            "name_edit_save": (64, 24),
            "name_edit_save_disabled": (64, 24),
            "name_edit_cancel": (64, 24),
        }
        assets: dict[str, pygame.Surface] = {}
        for key, filename in names.items():
            path = root / filename
            try:
                assets[key] = pygame.image.load(str(path)).convert_alpha()
            except (FileNotFoundError, pygame.error):
                size = fallbacks.get(key)
                if size is None:
                    rect = MENU_ASSET_RECTS.get(key, pygame.Rect(0, 0, 16, 16))
                    size = (max(1, rect.w), 16)
                fallback = pygame.Surface(size, pygame.SRCALPHA)
                fallback.fill((35, 42, 58, 255))
                assets[key] = fallback
        return assets

    def _load_player_preview_frame(self):
        if self._idle_body_frame is not None:
            return
        sprite = self.context.player_animation_path()
        try:
            frames = load_spritesheet_frames(sprite)
        except (FileNotFoundError, pygame.error):
            self._idle_body_frame = None
            return
        self._idle_body_frame = frames["idle_front"][0]

    def _start_browser(self):
        self._stop_browser()
        try:
            self._browser = LobbyBrowser(discovery_port=self.context.discovery_port)
            self._browser.start()
        except OSError:
            self._browser = None
            self.context.set_status("Could not listen for LAN rooms.", duration=3.0)

    def _stop_browser(self):
        if self._browser is None:
            return
        self._browser.stop()
        self._browser = None

    def _is_name_valid(self) -> bool:
        return protocol.is_valid_player_name(self.name_input)

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
        font: pygame.font.Font,
        text: str,
        rect: pygame.Rect,
        color: tuple[int, int, int],
        shadow: bool = True,
    ):
        text = self._fit_text(text, font, rect.w - 4)
        if shadow:
            shade = font.render(text, False, (8, 14, 25))
            surface.blit(shade, shade.get_rect(center=(rect.centerx + 1, rect.centery + 1)))
        label = font.render(text, False, color)
        surface.blit(label, label.get_rect(center=rect.center))

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

    def _draw_window_text_center(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        shadow: bool = True,
    ):
        rect = self._scale_rect(logical_rect)
        font = self._window_font(logical_size)
        text = self._fit_text(text, font, rect.w - (4 * self._window_scale()))
        if shadow:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, shade.get_rect(center=(rect.centerx + self._window_scale(), rect.centery + self._window_scale())))
        label = font.render(text, True, color)
        surface.blit(label, label.get_rect(center=rect.center))

    def _settings_layout(self):
        box = pygame.Rect(80, 12, 160, 156)
        dropdown = pygame.Rect(box.x + 15, box.y + 32, box.w - 30, 18)
        self._resolution_rects = []
        if self._settings_dropdown_open:
            option_y = dropdown.bottom
            for index, scale in enumerate(reversed(DisplayConfig.SUPPORTED_SCALES)):
                rect = pygame.Rect(dropdown.x, option_y + index * 11, dropdown.w, 11)
                self._resolution_rects.append((rect, scale))
        fullscreen = pygame.Rect(box.x + 15, box.y + 111, box.w - 30, 18)
        apply = pygame.Rect(box.x + 18, box.bottom - 26, 56, 18)
        close = pygame.Rect(box.right - 74, box.bottom - 26, 56, 18)
        return box, dropdown, fullscreen, close, apply

    def _name_edit_layout(self) -> dict[str, pygame.Rect]:
        frame_asset = self._assets.get("name_edit_frame")
        field_asset = self._assets.get("name_edit_field")
        button_asset = self._assets.get("name_edit_save")
        frame_w, frame_h = frame_asset.get_size() if frame_asset is not None else (148, 84)
        field_w, field_h = field_asset.get_size() if field_asset is not None else (134, 18)
        button_w, button_h = button_asset.get_size() if button_asset is not None else (64, 24)
        frame = pygame.Rect((320 - frame_w) // 2, (180 - frame_h) // 2, frame_w, frame_h)
        title = pygame.Rect(frame.x + 7, frame.y + 7, frame.w - 14, 16)
        field = pygame.Rect(frame.centerx - field_w // 2, title.bottom + 2, field_w, field_h)
        button_y = field.bottom + 8
        button_gap = 8
        total_button_w = button_w * 2 + button_gap
        save = pygame.Rect(frame.centerx - total_button_w // 2, button_y, button_w, button_h)
        cancel = pygame.Rect(save.right + button_gap, button_y, button_w, button_h)
        count_w = 36
        return {
            "frame": frame,
            "title": title,
            "field": field,
            "text": pygame.Rect(field.x + 5, field.y + 3, max(4, field.w - 17 - count_w), 12),
            "count": pygame.Rect(field.right - 7 - count_w, field.y + 3, count_w, 12),
            "save": save,
            "cancel": cancel,
        }

    def _open_name_edit_window(self):
        self._name_edit_original = self.name_input
        self._name_edit_value = self.name_input
        self._name_edit_open = True
        self._name_edit_field_active = False

    def _close_name_edit_window(self):
        self._name_edit_open = False
        self._name_edit_field_active = False

    def _name_edit_save_enabled(self) -> bool:
        return self._name_edit_value != self._name_edit_original and protocol.is_valid_player_name(self._name_edit_value)

    def _save_name_edit(self):
        if not self._name_edit_save_enabled():
            return
        self.name_input = self._name_edit_value
        self.context.player_name = self.name_input
        self.context.room_name = f"{self.context.player_name}Room"
        self.context.save_profile()
        self._close_name_edit_window()

    def _play(self):
        if not self._is_name_valid():
            self.context.set_status(
                f"Name must be {protocol.PLAYER_NAME_MIN_LEN}-{protocol.PLAYER_NAME_MAX_LEN} chars: letters, numbers, _ or -.",
                duration=3.0,
            )
            return
        self.context.player_name = self.name_input
        self.context.room_name = f"{self.context.player_name}Room"
        self.context.save_profile()
        self.switch("browse_lobby")

    def handle_event(self, event):
        super().handle_event(event)
        if self._name_edit_open:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._close_name_edit_window()
                elif event.key == pygame.K_RETURN:
                    if self._name_edit_save_enabled():
                        self._save_name_edit()
                elif not self._name_edit_field_active:
                    pass
                elif event.key == pygame.K_BACKSPACE:
                    if event_has_ctrl_modifier(event):
                        self._name_edit_value = remove_previous_input_token(self._name_edit_value, separators="_-")
                    else:
                        self._name_edit_value = self._name_edit_value[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self._name_edit_value = filter_player_name_input(self._name_edit_value + event.unicode)
                return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                layout = self._name_edit_layout()
                if layout["cancel"].collidepoint(event.pos):
                    self._close_name_edit_window()
                    return
                if layout["save"].collidepoint(event.pos):
                    self._save_name_edit()
                    return
                if layout["field"].collidepoint(event.pos):
                    self._name_edit_field_active = True
                    return
                if layout["frame"].collidepoint(event.pos):
                    self._name_edit_field_active = False
                    return
                return

        if self._settings_open:
            box, dropdown, fullscreen, close, apply = self._settings_layout()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not box.collidepoint(event.pos):
                    self._settings_open = False
                    self._settings_dropdown_open = False
                    return
                for rect, scale in self._resolution_rects:
                    if rect.collidepoint(event.pos):
                        self._pending_scale = scale
                        self._settings_dropdown_open = False
                        return
                if dropdown.collidepoint(event.pos):
                    self._settings_dropdown_open = not self._settings_dropdown_open
                    return
                if fullscreen.collidepoint(event.pos):
                    self._settings_dropdown_open = False
                    self._pending_fullscreen = not self._pending_fullscreen
                    return
                if close.collidepoint(event.pos):
                    self._settings_open = False
                    self._settings_dropdown_open = False
                    return
                if apply.collidepoint(event.pos):
                    if self.context.apply_display_settings(self._pending_scale, self._pending_fullscreen):
                        self._settings_open = False
                        self._settings_dropdown_open = False
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._settings_open = False
                self._settings_dropdown_open = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if NAME_DISPLAY_RECT.collidepoint(event.pos):
                self._open_name_edit_window()
                return
            if MENU_ASSET_RECTS["avatar_button"].collidepoint(event.pos):
                self.switch("avatar_setup")
                return
            if MENU_ASSET_RECTS["play"].collidepoint(event.pos):
                self._play()
                return
            if MENU_ASSET_RECTS["exit"].collidepoint(event.pos):
                self.context.running = False
                return
            if MENU_ASSET_RECTS["settings"].collidepoint(event.pos):
                if self.context.display_manager is not None:
                    self._pending_scale = self.context.display_manager.config.selected_scale
                    self._pending_fullscreen = self.context.display_manager.config.fullscreen
                self._settings_dropdown_open = False
                self._settings_open = True
                return

    def update(self, dt: float):
        _ = dt
        self._presence_entries = self._browser.presence_snapshot() if self._browser is not None else []

        mp = self.context.mouse_pos
        self._hovered = None
        if self._name_edit_open:
            return
        if NAME_DISPLAY_RECT.collidepoint(mp):
            self._hovered = "name"
            return
        for key in ("avatar_button", "play", "exit", "settings"):
            if MENU_ASSET_RECTS[key].collidepoint(mp):
                self._hovered = key
                return

    def draw(self, surface):
        background = self._assets.get("background")
        if background is not None:
            surface.blit(background, MENU_ASSET_RECTS["background"])
        else:
            surface.fill(DEFAULT_THEME.bg)

        self._draw_asset(surface, "crown")
        self._draw_asset(surface, "title")
        self._draw_avatar_panel(surface)
        self._draw_center_buttons(surface)
        self._draw_online_panel(surface)

        if self._name_edit_open:
            self._draw_name_edit_dialog(surface)

    def _draw_asset(self, surface: pygame.Surface, key: str):
        asset = self._assets.get(key)
        rect = MENU_ASSET_RECTS[key]
        if asset is None:
            return
        surface.blit(asset, rect)

    def _draw_hover_outline(self, surface: pygame.Surface, rect: pygame.Rect):
        pygame.draw.rect(surface, (115, 190, 255), rect.inflate(2, 2), width=1, border_radius=2)

    def _draw_avatar_panel(self, surface: pygame.Surface):
        for key in ("avatar_section", "avatar_bg", "avatar_frame"):
            self._draw_asset(surface, key)

        if self._idle_body_frame is None:
            self._draw_asset(surface, "avatar_model")
        self._draw_asset(surface, "avatar_platform")
        self._draw_asset(surface, "avatar_button")
        if self._hovered == "avatar_button":
            self._draw_hover_outline(surface, MENU_ASSET_RECTS["avatar_button"])

    def _draw_center_buttons(self, surface: pygame.Surface):
        self._draw_asset(surface, "play")
        self._draw_asset(surface, "exit")
        self._draw_asset(surface, "settings")

        if self._hovered == "play":
            self._draw_hover_outline(surface, MENU_ASSET_RECTS["play"])
        elif self._hovered == "exit":
            self._draw_hover_outline(surface, MENU_ASSET_RECTS["exit"])
        elif self._hovered == "settings":
            self._draw_hover_outline(surface, MENU_ASSET_RECTS["settings"])

    def _draw_online_panel(self, surface: pygame.Surface):
        self._draw_asset(surface, "online_section")

        card_asset = self._assets.get("online_card")
        for index, _entry in enumerate(self._online_entries()[: len(ONLINE_CARD_RECTS)]):
            rect = ONLINE_CARD_RECTS[index]
            if card_asset is not None:
                surface.blit(card_asset, rect)

    def _online_entries(self) -> list[tuple[str, str, tuple[int, int, int]]]:
        entries = []
        seen_presence_ids = {self.context.presence_instance_id}
        seen_names = {self.name_input}
        for entry in self._presence_entries:
            if entry.instance_id in seen_presence_ids:
                continue
            if entry.player_name in seen_names:
                continue
            seen_presence_ids.add(entry.instance_id)
            seen_names.add(entry.player_name)
            entries.append((entry.player_name, self._presence_status_label(entry.status), self._presence_status_color(entry.status)))
            if len(entries) >= len(ONLINE_CARD_RECTS):
                break
        return entries

    def _presence_status_label(self, status: int) -> str:
        if status == protocol.PRESENCE_STATUS_IN_GAME:
            return "IN GAME"
        if status == protocol.PRESENCE_STATUS_LOBBY:
            return "IN LOBBY"
        return "ONLINE"

    def _presence_status_color(self, status: int) -> tuple[int, int, int]:
        if status == protocol.PRESENCE_STATUS_IN_GAME:
            return (220, 120, 100)
        if status == protocol.PRESENCE_STATUS_LOBBY:
            return (120, 180, 255)
        return (110, 220, 140)

    def _draw_settings(self, surface):
        box, dropdown, fullscreen, close, apply = self._settings_layout()
        scrim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        scrim.fill((8, 10, 18, 205))
        surface.blit(scrim, (0, 0))
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((4, 22, 38, 245))
        surface.blit(panel, box.topleft)
        pygame.draw.rect(surface, (13, 39, 63), box, width=3, border_radius=4)
        pygame.draw.rect(surface, (93, 150, 197), box, width=1, border_radius=4)

        display_group = pygame.Rect(box.x + 18, box.y + 24, box.w - 36, 86)
        pygame.draw.rect(surface, (3, 17, 31), display_group, border_radius=3)
        pygame.draw.rect(surface, (18, 54, 83), display_group, width=2, border_radius=3)

        pygame.draw.rect(surface, (2, 16, 29), dropdown, border_radius=2)
        pygame.draw.rect(surface, (24, 67, 101), dropdown, width=2, border_radius=2)
        arrow_box = pygame.Rect(dropdown.right - 28, dropdown.y, 28, dropdown.h)
        pygame.draw.rect(surface, (6, 28, 47), arrow_box)
        pygame.draw.line(surface, (24, 67, 101), arrow_box.topleft, arrow_box.bottomleft, 1)
        tri = [
            (arrow_box.centerx - 5, arrow_box.centery - 2),
            (arrow_box.centerx + 5, arrow_box.centery - 2),
            (arrow_box.centerx, arrow_box.centery + 4),
        ]
        pygame.draw.polygon(surface, (230, 238, 248), tri)

        if self._settings_dropdown_open:
            for rect, scale in self._resolution_rects:
                selected = scale == self._pending_scale
                fill = (6, 80, 170) if selected else (2, 17, 31)
                pygame.draw.rect(surface, fill, rect)
                pygame.draw.line(surface, (21, 70, 113), rect.topleft, rect.topright, 1)
            if self._resolution_rects:
                menu_rect = self._resolution_rects[0][0].unionall([rect for rect, _scale in self._resolution_rects])
                pygame.draw.rect(surface, (24, 67, 101), menu_rect, width=2, border_radius=2)

        pygame.draw.rect(surface, (3, 17, 31), fullscreen, border_radius=3)
        pygame.draw.rect(surface, (18, 54, 83), fullscreen, width=2, border_radius=3)
        toggle = pygame.Rect(fullscreen.right - 54, fullscreen.y + 4, 46, fullscreen.h - 8)
        pygame.draw.rect(surface, (7, 88, 185) if self._pending_fullscreen else (64, 68, 74), toggle, border_radius=3)
        pygame.draw.rect(surface, (86, 151, 255), toggle, width=1, border_radius=3)
        knob_x = toggle.right - 14 if self._pending_fullscreen else toggle.x + 2
        pygame.draw.rect(surface, (232, 236, 238), pygame.Rect(knob_x, toggle.y + 2, 12, toggle.h - 4), border_radius=3)

        for rect, variant in ((apply, "primary"), (close, "neutral")):
            fill = (10, 87, 190) if variant == "primary" else (80, 80, 80)
            pygame.draw.rect(surface, fill, rect, border_radius=3)
            pygame.draw.rect(surface, (108, 164, 255) if variant == "primary" else (150, 150, 150), rect, width=2, border_radius=3)

    def _draw_window_settings_panel(self, surface: pygame.Surface):
        box, dropdown, fullscreen, close, apply = self._settings_layout()
        scale = self._window_scale()
        box_w = self._scale_rect(box)
        dropdown_w = self._scale_rect(dropdown)
        fullscreen_w = self._scale_rect(fullscreen)
        close_w = self._scale_rect(close)
        apply_w = self._scale_rect(apply)

        scrim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        scrim.fill((8, 10, 18, 205))
        surface.blit(scrim, (0, 0))

        panel = pygame.Surface(box_w.size, pygame.SRCALPHA)
        panel.fill((4, 22, 38, 245))
        surface.blit(panel, box_w.topleft)
        pygame.draw.rect(surface, (13, 39, 63), box_w, width=max(2, 3 * scale), border_radius=4 * scale)
        pygame.draw.rect(surface, (93, 150, 197), box_w, width=max(1, scale), border_radius=4 * scale)

        display_group = self._scale_rect(pygame.Rect(box.x + 10, box.y + 24, box.w - 20, 84))
        pygame.draw.rect(surface, (3, 17, 31), display_group, border_radius=3 * scale)
        pygame.draw.rect(surface, (18, 54, 83), display_group, width=max(1, 2 * scale), border_radius=3 * scale)

        pygame.draw.rect(surface, (2, 16, 29), dropdown_w, border_radius=2 * scale)
        pygame.draw.rect(surface, (24, 67, 101), dropdown_w, width=max(1, 2 * scale), border_radius=2 * scale)
        arrow_box = pygame.Rect(dropdown_w.right - 28 * scale, dropdown_w.y, 28 * scale, dropdown_w.h)
        pygame.draw.rect(surface, (6, 28, 47), arrow_box)
        pygame.draw.line(surface, (24, 67, 101), arrow_box.topleft, arrow_box.bottomleft, max(1, scale))
        tri = [
            (arrow_box.centerx - 5 * scale, arrow_box.centery - 2 * scale),
            (arrow_box.centerx + 5 * scale, arrow_box.centery - 2 * scale),
            (arrow_box.centerx, arrow_box.centery + 4 * scale),
        ]
        pygame.draw.polygon(surface, (230, 238, 248), tri)

        if self._settings_dropdown_open:
            option_rects = []
            for rect, option_scale in self._resolution_rects:
                rect_w = self._scale_rect(rect)
                option_rects.append(rect_w)
                selected = option_scale == self._pending_scale
                fill = (6, 80, 170) if selected else (2, 17, 31)
                pygame.draw.rect(surface, fill, rect_w)
                pygame.draw.line(surface, (21, 70, 113), rect_w.topleft, rect_w.topright, max(1, scale))
            if option_rects:
                menu_rect = option_rects[0].unionall(option_rects)
                pygame.draw.rect(surface, (24, 67, 101), menu_rect, width=max(1, 2 * scale), border_radius=2 * scale)

        pygame.draw.rect(surface, (3, 17, 31), fullscreen_w, border_radius=3 * scale)
        pygame.draw.rect(surface, (18, 54, 83), fullscreen_w, width=max(1, 2 * scale), border_radius=3 * scale)
        toggle = pygame.Rect(fullscreen_w.right - 46 * scale, fullscreen_w.y + 4 * scale, 40 * scale, fullscreen_w.h - 8 * scale)
        pygame.draw.rect(surface, (7, 88, 185) if self._pending_fullscreen else (64, 68, 74), toggle, border_radius=3 * scale)
        pygame.draw.rect(surface, (86, 151, 255), toggle, width=max(1, scale), border_radius=3 * scale)
        knob_x = toggle.right - 12 * scale if self._pending_fullscreen else toggle.x + 2 * scale
        pygame.draw.rect(surface, (232, 236, 238), pygame.Rect(knob_x, toggle.y + 2 * scale, 10 * scale, toggle.h - 4 * scale), border_radius=3 * scale)

        for rect, variant in ((apply_w, "primary"), (close_w, "neutral")):
            fill = (10, 87, 190) if variant == "primary" else (80, 80, 80)
            pygame.draw.rect(surface, fill, rect, border_radius=3 * scale)
            pygame.draw.rect(surface, (108, 164, 255) if variant == "primary" else (150, 150, 150), rect, width=max(1, 2 * scale), border_radius=3 * scale)

    def _draw_dialog_asset(self, surface: pygame.Surface, key: str, rect: pygame.Rect):
        asset = self._assets.get(key)
        if asset is None:
            return
        if asset.get_size() == rect.size:
            surface.blit(asset, rect)
        else:
            surface.blit(pygame.transform.scale(asset, rect.size), rect)

    def _draw_name_edit_dialog(self, surface: pygame.Surface):
        layout = self._name_edit_layout()
        scrim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 145))
        surface.blit(scrim, (0, 0))
        self._draw_dialog_asset(surface, "name_edit_frame", layout["frame"])
        self._draw_dialog_asset(surface, "name_edit_field", layout["field"])
        save_asset = "name_edit_save" if self._name_edit_save_enabled() else "name_edit_save_disabled"
        self._draw_dialog_asset(surface, save_asset, layout["save"])
        self._draw_dialog_asset(surface, "name_edit_cancel", layout["cancel"])

        mp = self.context.mouse_pos
        if self._name_edit_field_active:
            self._draw_hover_outline(surface, layout["field"])
        if self._name_edit_save_enabled() and layout["save"].collidepoint(mp):
            self._draw_hover_outline(surface, layout["save"])
        if layout["cancel"].collidepoint(mp):
            self._draw_hover_outline(surface, layout["cancel"])

    def draw_window_overlay(self, surface: pygame.Surface):
        if self._settings_open:
            self._draw_window_settings_panel(surface)
            self._draw_window_settings_text(surface)
            self._draw_window_global_messages(surface)
            return
        if self._name_edit_open:
            self._draw_window_name_edit_dialog(surface)
            self._draw_window_global_messages(surface)
            return
        self._draw_window_avatar_text(surface)
        self._draw_window_center_text(surface)
        self._draw_window_online_text(surface)
        self._draw_window_global_messages(surface)

    def _draw_window_avatar_text(self, surface: pygame.Surface):
        color = (255, 236, 170) if self._hovered == "name" else (190, 220, 255)
        self._draw_window_text_center(surface, 6, self.name_input, NAME_DISPLAY_RECT, color)
        self._draw_window_text_center(surface, 7, "AVATAR", MENU_ASSET_RECTS["avatar_button"], (245, 247, 252))
        self._draw_window_avatar_preview(surface)

    def _current_avatar_source(self) -> pygame.Surface:
        return self.context.current_avatar_source()

    def _draw_window_avatar_preview(self, surface: pygame.Surface):
        if self._idle_body_frame is None:
            return
        model_rect = MENU_ASSET_RECTS["avatar_model"]
        frame_rect = self._scale_rect(
            pygame.Rect(model_rect.x, model_rect.y, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT)
        )
        avatar_logical = pygame.Rect(
            model_rect.x + AVATAR_RECT.x,
            model_rect.y + AVATAR_RECT.y,
            AVATAR_RECT.w,
            AVATAR_RECT.h,
        )
        avatar_rect = self._scale_rect(avatar_logical)
        avatar = pygame.transform.smoothscale(crop_square(self._current_avatar_source()), avatar_rect.size)
        body = pygame.transform.scale(self._idle_body_frame, frame_rect.size)
        surface.blit(avatar, avatar_rect)
        surface.blit(body, frame_rect)

    def _draw_window_center_text(self, surface: pygame.Surface):
        play_color = (190, 225, 255) if self._is_name_valid() else (120, 130, 150)
        self._draw_window_text_center(surface, 13, "PLAY", MENU_ASSET_RECTS["play"], play_color)
        self._draw_window_text_center(surface, 8, "EXIT", MENU_ASSET_RECTS["exit"], (220, 235, 250))

    def _draw_window_online_text(self, surface: pygame.Surface):
        self._draw_window_text_center(surface, 7, "ONLINE", pygame.Rect(248, 20, 56, 11), (150, 205, 255))
        entries = self._online_entries()
        for index, rect in enumerate(ONLINE_CARD_RECTS):
            if index >= len(entries):
                continue
            name, status, color = entries[index]
            self._draw_window_text_center(surface, 7, name, pygame.Rect(rect.x + 3, rect.y + 3, rect.w - 6, 8), (245, 247, 252), shadow=False)
            self._draw_window_text_center(surface, 7, status, pygame.Rect(rect.x + 3, rect.y + 13, rect.w - 6, 8), color, shadow=False)

    def _draw_window_settings_text(self, surface: pygame.Surface):
        box, dropdown, fullscreen, close, apply = self._settings_layout()
        text = (207, 229, 250)
        muted = (154, 185, 214)
        self._draw_window_text_center(surface, 12, "SETTINGS", pygame.Rect(box.x + 10, box.y + 9, box.w - 20, 14), text, shadow=False)
        self._draw_window_text_left(surface, 7, "DISPLAY SETTINGS", pygame.Rect(box.x + 28, box.y + 25, box.w - 56, 10), text, shadow=False)
        self._draw_window_text_left(surface, 7, RESOLUTION_LABELS[self._pending_scale], pygame.Rect(dropdown.x + 8, dropdown.y + 2, dropdown.w - 38, dropdown.h - 4), text, shadow=False)
        for rect, scale in self._resolution_rects:
            color = text if scale == self._pending_scale else muted
            self._draw_window_text_left(surface, 6, RESOLUTION_LABELS[scale], pygame.Rect(rect.x + 8, rect.y, rect.w - 12, rect.h), color, shadow=False)
        self._draw_window_text_left(surface, 7, "FULLSCREEN", pygame.Rect(fullscreen.x + 12, fullscreen.y + 5, 100, 12), text, shadow=False)
        self._draw_window_text_center(surface, 7, "ON" if self._pending_fullscreen else "OFF", pygame.Rect(fullscreen.right - 54, fullscreen.y + 4, 28, fullscreen.h - 8), text, shadow=False)
        self._draw_window_text_center(surface, 9, "APPLY", apply, (248, 250, 255), shadow=True)
        self._draw_window_text_center(surface, 9, "CLOSE", close, (220, 226, 236), shadow=True)

    def _draw_window_text_left(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        shadow: bool = False,
    ):
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size)
        text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        y = rect.y + (rect.h - font.get_height()) // 2
        if shadow:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, (rect.x + scale, y + scale))
        label = font.render(text, True, color)
        surface.blit(label, (rect.x, y))

    def _draw_window_text_caret(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
    ):
        if int(pygame.time.get_ticks() / 500) % 2 != 0:
            return
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size)
        fitted_text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        text_width = font.size(fitted_text)[0] if fitted_text else 0
        caret_w = max(1, scale)
        caret_h = max(caret_w, font.get_height() - (2 * scale))
        x = min(rect.right - caret_w, rect.x + text_width + scale)
        y = rect.y + (rect.h - caret_h) // 2
        pygame.draw.rect(surface, color, pygame.Rect(x, y, caret_w, caret_h))

    def _draw_window_text_right_alpha(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        alpha: int,
    ):
        rect = self._scale_rect(logical_rect)
        font = self._window_font(logical_size)
        label = font.render(text, True, color)
        label.set_alpha(alpha)
        y = rect.y + (rect.h - font.get_height()) // 2
        surface.blit(label, (rect.right - label.get_width(), y))

    def _draw_window_name_edit_dialog(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        layout = self._name_edit_layout()
        save_enabled = self._name_edit_save_enabled()
        self._draw_window_text_center(surface, 7, "EDIT NAME", layout["title"], (180, 220, 255))
        self._draw_window_text_left(surface, 7, self._name_edit_value, layout["text"], theme.text, shadow=False)
        self._draw_window_text_right_alpha(
            surface,
            7,
            f"{len(self._name_edit_value)}/{protocol.PLAYER_NAME_MAX_LEN}",
            layout["count"],
            theme.text_muted,
            191,
        )
        if self._name_edit_field_active:
            self._draw_window_text_caret(surface, 7, self._name_edit_value, layout["text"], theme.text)
        save_color = theme.text if save_enabled else theme.text_muted
        self._draw_window_text_center(surface, 7, "SAVE", layout["save"], save_color)
        self._draw_window_text_center(surface, 7, "CANCEL", layout["cancel"], theme.text)

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
