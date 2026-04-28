import pygame

from network import protocol
from states.common import ScreenState, alnum_only
from ui import components as ui
from ui.theme import DEFAULT_THEME


class MainMenuState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.name_active = False
        self.name_input = context.player_name
        self.host_button = ui.Button(pygame.Rect(0, 0, 220, 48), "Host Room")
        self.join_button = ui.Button(pygame.Rect(0, 0, 220, 48), "Join Room")
        self.name_rect = pygame.Rect(0, 0, 320, 44)
        self._host_h = False
        self._join_h = False

    def enter(self):
        self.context.detach_network(send_disconnect=False)
        self.context.stop_server()

    def _layout(self):
        width, height = self.context.screen.get_size()
        self.name_rect.center = (width // 2, height // 2 - 60)
        self.host_button.rect.center = (width // 2, height // 2 + 10)
        self.join_button.rect.center = (width // 2, height // 2 + 72)

    def _is_name_valid(self) -> bool:
        return protocol.is_valid_player_name(self.name_input)

    def handle_event(self, event):
        super().handle_event(event)
        self._layout()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.name_active = self.name_rect.collidepoint(event.pos)
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
        mp = pygame.mouse.get_pos()
        self._host_h = self.host_button.rect.collidepoint(mp)
        self._join_h = self.join_button.rect.collidepoint(mp)

    def draw(self, surface):
        super().draw(surface)
        self._layout()
        theme = DEFAULT_THEME

        title = self.context.title_font.render("Tower Jump LAN", True, theme.text)
        surface.blit(title, title.get_rect(center=(surface.get_width() // 2, 100)))
        sub = self.context.small_font.render("Multiplayer lobby", True, theme.text_muted)
        surface.blit(sub, sub.get_rect(center=(surface.get_width() // 2, 142)))

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
