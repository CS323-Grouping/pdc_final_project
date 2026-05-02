import pygame

from app.display import DisplayConfig
from network import protocol
from states.common import ScreenState, alnum_only
from ui import components as ui
from ui.theme import DEFAULT_THEME


RESOLUTION_LABELS = {
    2: "640x360",
    3: "960x540",
    4: "1280x720",
    5: "1600x900",
    6: "1920x1080",
}


class MainMenuState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.name_active = False
        self.name_input = context.player_name
        self.host_button = ui.Button(pygame.Rect(0, 0, 220, 48), "Host Room")
        self.join_button = ui.Button(pygame.Rect(0, 0, 220, 48), "Join Room")
        self.avatar_button = ui.Button(pygame.Rect(0, 0, 140, 38), "Avatar")
        self.settings_button = ui.Button(pygame.Rect(0, 0, 140, 38), "Settings")
        self.apply_button = ui.Button(pygame.Rect(0, 0, 120, 38), "Apply")
        self.close_settings_button = ui.Button(pygame.Rect(0, 0, 120, 38), "Close")
        self.fullscreen_button = ui.Button(pygame.Rect(0, 0, 170, 38), "Fullscreen: Off")
        self.name_rect = pygame.Rect(0, 0, 320, 44)
        self._host_h = False
        self._join_h = False
        self._avatar_h = False
        self._settings_h = False
        self._apply_h = False
        self._close_settings_h = False
        self._fullscreen_h = False
        self._settings_open = False
        self._pending_scale = context.display_manager.config.selected_scale if context.display_manager else 4
        self._pending_fullscreen = context.display_manager.config.fullscreen if context.display_manager else False
        self._resolution_rects: list[tuple[pygame.Rect, int]] = []

    def enter(self):
        self.context.detach_network(send_disconnect=False)
        self.context.stop_server()

    def _layout(self):
        width, height = self.context.screen.get_size()
        center_x = width // 2
        top = max(64, height // 2 - 170)
        self.avatar_button.rect.topleft = (16, 16)
        self.settings_button.rect.topright = (width - 16, 16)
        self.name_rect.center = (center_x, top + 110)
        self.host_button.rect.center = (center_x, top + 184)
        self.join_button.rect.center = (center_x, top + 246)

    def _settings_layout(self):
        width, height = self.context.screen.get_size()
        box = pygame.Rect(0, 0, min(560, width - 48), min(284, height - 48))
        box.center = (width // 2, height // 2)
        self._resolution_rects = []
        x = box.x + 24
        y = box.y + 94
        button_w = max(88, (box.w - 48 - 4 * 8) // 5)
        for scale in DisplayConfig.SUPPORTED_SCALES:
            rect = pygame.Rect(x, y, button_w, 36)
            self._resolution_rects.append((rect, scale))
            x += button_w + 8
        self.fullscreen_button.rect.topleft = (box.x + 24, box.y + 154)
        self.apply_button.rect.bottomright = (box.right - 24, box.bottom - 20)
        self.close_settings_button.rect.bottomright = (self.apply_button.rect.left - 12, box.bottom - 20)
        return box

    def _is_name_valid(self) -> bool:
        return protocol.is_valid_player_name(self.name_input)

    def handle_event(self, event):
        super().handle_event(event)
        self._layout()
        if self._settings_open:
            box = self._settings_layout()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not box.collidepoint(event.pos):
                    self._settings_open = False
                    return
                for rect, scale in self._resolution_rects:
                    if rect.collidepoint(event.pos):
                        self._pending_scale = scale
                        return
                if self.fullscreen_button.rect.collidepoint(event.pos):
                    self._pending_fullscreen = not self._pending_fullscreen
                    return
                if self.close_settings_button.rect.collidepoint(event.pos):
                    self._settings_open = False
                    return
                if self.apply_button.rect.collidepoint(event.pos):
                    if self.context.apply_display_settings(self._pending_scale, self._pending_fullscreen):
                        self._settings_open = False
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._settings_open = False
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.name_active = self.name_rect.collidepoint(event.pos)
            if self.avatar_button.rect.collidepoint(event.pos):
                self.switch("avatar_setup")
                return
            if self.settings_button.rect.collidepoint(event.pos):
                if self.context.display_manager is not None:
                    self._pending_scale = self.context.display_manager.config.selected_scale
                    self._pending_fullscreen = self.context.display_manager.config.fullscreen
                self._settings_open = True
                return
            if self.host_button.enabled and self.host_button.rect.collidepoint(event.pos):
                self.context.player_name = self.name_input
                self.context.room_name = f"{self.context.player_name}Room"
                self.switch("host_lobby")
            if self.join_button.enabled and self.join_button.rect.collidepoint(event.pos):
                self.context.player_name = self.name_input
                self.switch("browse_lobby")

        if event.type == pygame.KEYDOWN and self.name_active:
            if event.key == pygame.K_BACKSPACE:
                self.name_input = self.name_input[:-1]
            else:
                self.name_input = alnum_only(self.name_input + event.unicode, max_len=24)

    def update(self, dt: float):
        _ = dt
        valid = self._is_name_valid()
        self.host_button.enabled = valid
        self.join_button.enabled = valid
        mp = self.context.mouse_pos
        self._host_h = self.host_button.rect.collidepoint(mp)
        self._join_h = self.join_button.rect.collidepoint(mp)
        self._avatar_h = self.avatar_button.rect.collidepoint(mp)
        self._settings_h = self.settings_button.rect.collidepoint(mp)
        if self._settings_open:
            self._settings_layout()
            self._apply_h = self.apply_button.rect.collidepoint(mp)
            self._close_settings_h = self.close_settings_button.rect.collidepoint(mp)
            self._fullscreen_h = self.fullscreen_button.rect.collidepoint(mp)

    def draw(self, surface):
        super().draw(surface)
        self._layout()
        theme = DEFAULT_THEME
        width, height = surface.get_size()
        top = max(64, height // 2 - 170)

        title = self.context.title_font.render("Tower Jump LAN", True, theme.text)
        surface.blit(title, title.get_rect(center=(width // 2, top)))
        sub = self.context.small_font.render("Multiplayer lobby", True, theme.text_muted)
        surface.blit(sub, sub.get_rect(center=(width // 2, top + 40)))
        ui.draw_button(surface, self.context.small_font, self.avatar_button, theme, hovered=self._avatar_h, variant="neutral")
        ui.draw_button(surface, self.context.small_font, self.settings_button, theme, hovered=self._settings_h, variant="neutral")

        inp = ui.TextInput(self.name_rect, "Player name (alphanumeric, 3–24)", self.name_input, self.name_active)
        ui.draw_text_input(surface, (self.context.font, self.context.tiny_font), inp, theme)

        if not self._is_name_valid():
            warn = self.context.tiny_font.render(
                "Name must be 3–24 alphanumeric characters.",
                True,
                theme.text_warn,
            )
            surface.blit(warn, (self.name_rect.x, self.name_rect.y + self.name_rect.height + 8))

        ui.draw_button(surface, self.context.font, self.host_button, theme, hovered=self._host_h)
        ui.draw_button(surface, self.context.font, self.join_button, theme, hovered=self._join_h)
        if self._settings_open:
            self._draw_settings(surface)

    def _draw_settings(self, surface):
        theme = DEFAULT_THEME
        box = self._settings_layout()
        scrim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        scrim.fill(theme.overlay_scrim)
        surface.blit(scrim, (0, 0))
        pygame.draw.rect(surface, theme.bg_panel, box, border_radius=8)
        pygame.draw.rect(surface, theme.border, box, width=2, border_radius=8)

        title = self.context.font.render("Display Settings", True, theme.text)
        surface.blit(title, (box.x + 24, box.y + 22))
        current = self.context.display_manager.config if self.context.display_manager else None
        current_text = "Current: "
        if current is not None:
            current_text += f"{RESOLUTION_LABELS[current.selected_scale]} {'Fullscreen' if current.fullscreen else 'Windowed'}"
        else:
            current_text += "Windowed"
        surface.blit(self.context.tiny_font.render(current_text, True, theme.text_muted), (box.x + 24, box.y + 56))
        surface.blit(self.context.small_font.render("Resolution", True, theme.text), (box.x + 24, box.y + 72))

        for rect, scale in self._resolution_rects:
            selected = scale == self._pending_scale
            btn = ui.Button(rect, RESOLUTION_LABELS[scale], True)
            ui.draw_button(
                surface,
                self.context.tiny_font,
                btn,
                theme,
                hovered=rect.collidepoint(self.context.mouse_pos),
                variant="primary" if selected else "neutral",
            )

        self.fullscreen_button.text = f"Fullscreen: {'On' if self._pending_fullscreen else 'Off'}"
        ui.draw_button(surface, self.context.small_font, self.fullscreen_button, theme, hovered=self._fullscreen_h, variant="neutral")
        ui.draw_button(surface, self.context.small_font, self.close_settings_button, theme, hovered=self._close_settings_h, variant="neutral")
        ui.draw_button(surface, self.context.small_font, self.apply_button, theme, hovered=self._apply_h)
