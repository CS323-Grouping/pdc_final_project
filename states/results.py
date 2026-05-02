import pygame

from states.common import ScreenState
from ui import components as ui
from ui.theme import DEFAULT_THEME


class ResultsState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self._auto_hide = 5.0
        self._elapsed = 0.0

    def enter(self):
        self._auto_hide = 5.0
        self._elapsed = 0.0
        self.context.countdown_remaining = None

    def _placement_label(self, placement: int) -> str:
        if placement == 1:
            return "WINNER"
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(placement % 10 if placement % 100 not in (11, 12, 13) else 0, "th")
        return f"{placement}{suffix} place"

    def handle_event(self, event):
        super().handle_event(event)
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self._finish()

    def _finish(self):
        nxt = self.context.return_state_after_results or "menu"
        self.switch(nxt)

    def update(self, dt: float):
        self._elapsed += dt
        self._auto_hide -= dt
        if self._auto_hide <= 0:
            self._finish()

    def draw(self, surface):
        super().draw(surface)
        w, h = surface.get_size()
        theme = DEFAULT_THEME

        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill(theme.overlay_scrim)
        surface.blit(overlay, (0, 0))

        title = self.context.title_font.render("Results", True, theme.text)
        surface.blit(title, title.get_rect(center=(w // 2, 72)))

        ui.draw_results_table(
            surface,
            (self.context.font, self.context.small_font),
            self.context.results_standings,
            self._elapsed,
            self._placement_label,
            theme,
        )

        hint = self.context.tiny_font.render(
            f"Continue in {max(0, int(self._auto_hide + 0.99))}s · any key / click",
            True,
            theme.text_muted,
        )
        surface.blit(hint, hint.get_rect(center=(w // 2, h - 42)))
