from dataclasses import dataclass

import pygame

from world.constants import INTERNAL_HEIGHT, INTERNAL_WIDTH


@dataclass(frozen=True)
class DisplayConfig:
    internal_width: int = INTERNAL_WIDTH
    internal_height: int = INTERNAL_HEIGHT
    selected_scale: int = 4
    fullscreen: bool = False

    SUPPORTED_SCALES = (2, 3, 4, 5, 6)

    def __post_init__(self):
        if self.selected_scale not in self.SUPPORTED_SCALES:
            raise ValueError(f"Unsupported display scale: {self.selected_scale}")

    @property
    def internal_size(self) -> tuple[int, int]:
        return self.internal_width, self.internal_height

    @property
    def window_size(self) -> tuple[int, int]:
        return (
            self.internal_width * self.selected_scale,
            self.internal_height * self.selected_scale,
        )


def choose_default_scale(display_size: tuple[int, int]) -> int:
    display_w, display_h = display_size
    fitting_scales = [
        scale
        for scale in DisplayConfig.SUPPORTED_SCALES
        if INTERNAL_WIDTH * scale <= display_w and INTERNAL_HEIGHT * scale <= display_h
    ]
    if not fitting_scales:
        return DisplayConfig.SUPPORTED_SCALES[0]
    max_scale = max(fitting_scales)
    if max_scale == 6 and INTERNAL_WIDTH * max_scale == display_w and INTERNAL_HEIGHT * max_scale == display_h:
        return 4
    if max_scale > 2 and INTERNAL_WIDTH * max_scale == display_w and INTERNAL_HEIGHT * max_scale == display_h:
        return max_scale - 1
    return min(max_scale, 4)


class DisplayManager:
    def __init__(self, config: DisplayConfig):
        self.config = config
        self.screen = self._set_mode(config)
        self.internal_surface = pygame.Surface(config.internal_size).convert()
        pygame.display.set_caption("Tower Jump LAN")

    def _set_mode(self, config: DisplayConfig) -> pygame.Surface:
        flags = pygame.FULLSCREEN if config.fullscreen else 0
        return pygame.display.set_mode(config.window_size, flags)

    @classmethod
    def create_default(cls) -> "DisplayManager":
        info = pygame.display.Info()
        scale = choose_default_scale((info.current_w, info.current_h))
        return cls(DisplayConfig(selected_scale=scale, fullscreen=False))

    def begin_frame(self) -> pygame.Surface:
        return self.internal_surface

    def blit_internal_to_window(self) -> pygame.Surface:
        scaled = pygame.transform.scale(self.internal_surface, self.config.window_size)
        self.screen.blit(scaled, (0, 0))
        return self.screen

    def present(self) -> None:
        self.blit_internal_to_window()
        pygame.display.flip()

    def begin_window_frame(self) -> pygame.Surface:
        return self.screen

    def present_window(self) -> None:
        pygame.display.flip()

    def window_to_internal(self, pos: tuple[int, int]) -> tuple[int, int]:
        x, y = pos
        return x // self.config.selected_scale, y // self.config.selected_scale

    def apply_config(self, config: DisplayConfig) -> pygame.Surface:
        previous_config = self.config
        previous_screen = self.screen
        previous_internal_surface = self.internal_surface
        try:
            screen = self._set_mode(config)
        except pygame.error:
            self.config = previous_config
            self.screen = previous_screen
            self.internal_surface = previous_internal_surface
            raise
        self.config = config
        self.screen = screen
        self.internal_surface = pygame.Surface(config.internal_size).convert()
        pygame.display.set_caption("Tower Jump LAN")
        return self.screen
