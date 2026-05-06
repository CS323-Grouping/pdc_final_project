import pygame

from app.display import DisplayConfig
from network import protocol
from network.discovery import LobbyBrowser, PresenceEntry
from player_scripts.animation import load_spritesheet_frames
from player_scripts.avatar_sprite import AVATAR_RECT, crop_square, make_default_avatar
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
    "avatar_section": pygame.Rect(10, 66, 68, 100),
    "avatar_bg": pygame.Rect(21, 88, 46, 46),
    "avatar_frame": pygame.Rect(19, 86, 50, 50),
    "avatar_model": pygame.Rect(33, 91, 22, 32),
    "avatar_platform": pygame.Rect(24, 123, 40, 8),
    "avatar_button": pygame.Rect(17, 141, 54, 18),
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


class MainMenuState(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.name_active = False
        self.name_input = context.player_name
        self._settings_open = False
        self._pending_scale = context.display_manager.config.selected_scale if context.display_manager else 4
        self._pending_fullscreen = context.display_manager.config.fullscreen if context.display_manager else False
        self._resolution_rects: list[tuple[pygame.Rect, int]] = []
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
        }
        assets: dict[str, pygame.Surface] = {}
        for key, filename in names.items():
            path = root / filename
            try:
                assets[key] = pygame.image.load(str(path)).convert_alpha()
            except (FileNotFoundError, pygame.error):
                fallback = pygame.Surface((max(1, MENU_ASSET_RECTS.get(key, pygame.Rect(0, 0, 16, 16)).w), 16), pygame.SRCALPHA)
                fallback.fill((35, 42, 58, 255))
                assets[key] = fallback
        return assets

    def _load_player_preview_frame(self):
        if self._idle_body_frame is not None:
            return
        sprite = self.context.project_root / "assets" / "player" / "animation" / "playerAnimationNormal_Blue.png"
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
        box = pygame.Rect(30, 28, 260, 124)
        self._resolution_rects = []
        x = box.x + 12
        y = box.y + 44
        for scale in DisplayConfig.SUPPORTED_SCALES:
            rect = pygame.Rect(x, y, 42, 16)
            self._resolution_rects.append((rect, scale))
            x += 47
        fullscreen = pygame.Rect(box.x + 12, box.y + 72, 92, 16)
        close = pygame.Rect(box.right - 104, box.bottom - 24, 44, 16)
        apply = pygame.Rect(box.right - 56, box.bottom - 24, 44, 16)
        return box, fullscreen, close, apply

    def _play(self):
        if not self._is_name_valid():
            self.context.set_status(
                f"Name must be {protocol.PLAYER_NAME_MIN_LEN}-{protocol.PLAYER_NAME_MAX_LEN} chars: letters, numbers, _ or -.",
                duration=3.0,
            )
            return
        self.context.player_name = self.name_input
        self.context.room_name = f"{self.context.player_name}Room"
        self.switch("browse_lobby")

    def handle_event(self, event):
        super().handle_event(event)
        if self._settings_open:
            box, fullscreen, close, apply = self._settings_layout()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not box.collidepoint(event.pos):
                    self._settings_open = False
                    return
                for rect, scale in self._resolution_rects:
                    if rect.collidepoint(event.pos):
                        self._pending_scale = scale
                        return
                if fullscreen.collidepoint(event.pos):
                    self._pending_fullscreen = not self._pending_fullscreen
                    return
                if close.collidepoint(event.pos):
                    self._settings_open = False
                    return
                if apply.collidepoint(event.pos):
                    if self.context.apply_display_settings(self._pending_scale, self._pending_fullscreen):
                        self._settings_open = False
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._settings_open = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.name_active = MENU_ASSET_RECTS["avatar_frame"].collidepoint(event.pos)
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
                self._settings_open = True
                return

        if event.type == pygame.KEYDOWN and self.name_active:
            if event.key == pygame.K_ESCAPE:
                self.name_active = False
            elif event.key == pygame.K_RETURN:
                self.name_active = False
            elif event.key == pygame.K_BACKSPACE:
                if event_has_ctrl_modifier(event):
                    self.name_input = remove_previous_input_token(self.name_input, separators="_-")
                else:
                    self.name_input = self.name_input[:-1]
            elif event.unicode and event.unicode.isprintable():
                self.name_input = filter_player_name_input(self.name_input + event.unicode)

    def update(self, dt: float):
        _ = dt
        self._presence_entries = self._browser.presence_snapshot() if self._browser is not None else []

        mp = self.context.mouse_pos
        self._hovered = None
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

        if self._settings_open:
            self._draw_settings(surface)

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
        theme = DEFAULT_THEME
        box, fullscreen, close, apply = self._settings_layout()
        scrim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        scrim.fill((8, 10, 18, 205))
        surface.blit(scrim, (0, 0))
        pygame.draw.rect(surface, theme.bg_panel, box, border_radius=4)
        pygame.draw.rect(surface, theme.border_focus, box, width=1, border_radius=4)

        for rect, scale in self._resolution_rects:
            selected = scale == self._pending_scale
            fill = theme.accent if selected else theme.bg_input
            pygame.draw.rect(surface, fill, rect, border_radius=2)
            pygame.draw.rect(surface, theme.border, rect, width=1, border_radius=2)

        pygame.draw.rect(surface, theme.bg_input, fullscreen, border_radius=2)
        pygame.draw.rect(surface, theme.border, fullscreen, width=1, border_radius=2)

        for rect, label, variant in ((close, "CLOSE", "neutral"), (apply, "APPLY", "primary")):
            _ = label
            fill = theme.accent if variant == "primary" else theme.bg_input
            pygame.draw.rect(surface, fill, rect, border_radius=2)
            pygame.draw.rect(surface, theme.border, rect, width=1, border_radius=2)

    def draw_window_overlay(self, surface: pygame.Surface):
        if self._settings_open:
            self._draw_window_settings_text(surface)
            self._draw_window_global_messages(surface)
            return
        self._draw_window_avatar_text(surface)
        self._draw_window_center_text(surface)
        self._draw_window_online_text(surface)
        self._draw_window_global_messages(surface)

    def _draw_window_avatar_text(self, surface: pygame.Surface):
        name_rect = pygame.Rect(14, 74, 60, 10)
        color = (255, 236, 170) if self.name_active else (190, 220, 255)
        self._draw_window_text_center(surface, 6, self.name_input, name_rect, color)
        self._draw_window_text_center(surface, 7, "AVATAR", MENU_ASSET_RECTS["avatar_button"], (245, 247, 252))
        self._draw_window_avatar_preview(surface)

    def _current_avatar_source(self) -> pygame.Surface:
        if self.context.avatar_window_surface is not None:
            return self.context.avatar_window_surface
        if self.context.avatar_surface is not None:
            return self.context.avatar_surface
        return make_default_avatar()

    def _draw_window_avatar_preview(self, surface: pygame.Surface):
        if self._idle_body_frame is None:
            return
        frame_rect = self._scale_rect(pygame.Rect(32, 91, PLAYER_FRAME_WIDTH, PLAYER_FRAME_HEIGHT))
        avatar_logical = pygame.Rect(
            32 + AVATAR_RECT.x,
            91 + AVATAR_RECT.y,
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
        theme = DEFAULT_THEME
        box, fullscreen, close, apply = self._settings_layout()
        self._draw_window_text_center(surface, 8, "DISPLAY SETTINGS", pygame.Rect(box.x + 10, box.y + 10, box.w - 20, 12), theme.text, shadow=False)
        current = self.context.display_manager.config if self.context.display_manager else None
        current_text = "Current: "
        if current is not None:
            current_text += f"{RESOLUTION_LABELS[current.selected_scale]} {'Full' if current.fullscreen else 'Window'}"
        else:
            current_text += "Window"
        self._draw_window_text_center(surface, 7, current_text, pygame.Rect(box.x + 10, box.y + 25, box.w - 20, 10), theme.text_muted, shadow=False)
        for rect, scale in self._resolution_rects:
            self._draw_window_text_center(surface, 7, str(scale) + "x", rect, theme.text, shadow=False)
        self._draw_window_text_center(surface, 7, f"Fullscreen {'ON' if self._pending_fullscreen else 'OFF'}", fullscreen, theme.text, shadow=False)
        self._draw_window_text_center(surface, 7, "CLOSE", close, theme.text, shadow=False)
        self._draw_window_text_center(surface, 7, "APPLY", apply, theme.text, shadow=False)

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
