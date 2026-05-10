"""Banner / status / global-message HUD that floats over every screen.

Owns the message strings, fade timers, and bottom-dock layout. Owned by
``AppContext.messages`` and exposed via thin shims on AppContext for backward
compatibility with existing call sites.
"""

from __future__ import annotations

from typing import Callable, Optional

import pygame

from ui.messages import draw_banner_bar, draw_global_messages_bottom_dock
from ui.theme import DEFAULT_THEME, Theme


class MessageHud:
    def __init__(
        self,
        small_font: pygame.font.Font,
        tiny_font: pygame.font.Font,
        window_border_inset_provider: Callable[[], int],
        theme: Theme = DEFAULT_THEME,
    ):
        self._small_font = small_font
        self._tiny_font = tiny_font
        self._inset = window_border_inset_provider
        self._theme = theme

        self.banner_message: str = ""
        self.banner_timer: float = 0.0
        self.status_message: str = ""
        self.status_timer: float = 0.0
        self.dock_global_messages_bottom: bool = False

    def set_banner(self, message: str, duration: float = 4.0) -> None:
        self.banner_message = message
        self.banner_timer = duration

    def set_status(self, message: str, duration: float = 3.0) -> None:
        self.status_message = message
        self.status_timer = duration

    def tick(self, dt: float) -> None:
        if self.banner_timer > 0:
            self.banner_timer = max(0.0, self.banner_timer - dt)
            if self.banner_timer == 0:
                self.banner_message = ""
        if self.status_timer > 0:
            self.status_timer = max(0.0, self.status_timer - dt)
            if self.status_timer == 0:
                self.status_message = ""

    def reserved_bottom_strip_px(self) -> int:
        if not self.dock_global_messages_bottom:
            return 0
        margin = 8
        if self.banner_message and self.status_message:
            return margin + 22 + 2 + 30
        if self.banner_message:
            return margin + 30
        if self.status_message:
            return margin + 28
        return 0

    def draw(self, surface: Optional[pygame.Surface]) -> None:
        if surface is None:
            return
        inset = self._inset()
        if self.dock_global_messages_bottom:
            if self.banner_message or self.status_message:
                draw_global_messages_bottom_dock(
                    surface,
                    self._small_font,
                    self._tiny_font,
                    self.banner_message,
                    self.status_message,
                    inset,
                    self._theme,
                )
            return
        if self.banner_message:
            draw_banner_bar(surface, self._small_font, self.banner_message, horizontal_inset=inset)
        if self.status_message:
            y = 34 if self.banner_message else 8
            status_surface = self._tiny_font.render(self.status_message, True, (255, 230, 120))
            surface.blit(status_surface, (inset + 10, y))
