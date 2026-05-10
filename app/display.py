from dataclasses import dataclass
import logging
import sys

import pygame

from app.version import window_title
from world.constants import INTERNAL_HEIGHT, INTERNAL_WIDTH

LOGGER = logging.getLogger(__name__)


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


def desktop_size_for_default_scale() -> tuple[int, int]:
    """Pixels available for fitting the game window before the first real ``set_mode``.

    ``pygame.display.Info()`` is unreliable until a display surface exists (often
    reports 0×0 or stale values), which can pick a scale/window size that fails
    or renders as a blank window on some GPUs/drivers. Prefer OS APIs where
    possible, then prime SDL with a 1×1 hidden surface so ``Info()`` matches
    the primary monitor.
    """

    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            w = int(user32.GetSystemMetrics(0))
            h = int(user32.GetSystemMetrics(1))
            if w >= INTERNAL_WIDTH and h >= INTERNAL_HEIGHT:
                return (w, h)
        except Exception:
            pass

    hidden = getattr(pygame, "HIDDEN", 0)
    try:
        pygame.display.set_mode((1, 1), hidden)
    except (TypeError, pygame.error):
        try:
            pygame.display.set_mode((1, 1))
        except pygame.error:
            pass

    info = pygame.display.Info()
    w, h = int(info.current_w), int(info.current_h)
    if w >= INTERNAL_WIDTH and h >= INTERNAL_HEIGHT:
        return (w, h)
    LOGGER.warning(
        "Could not read desktop size reliably (got %sx%s); using 1280x720 for default scale.",
        w,
        h,
    )
    return (1280, 720)


class DisplayManager:
    def __init__(self, config: DisplayConfig):
        self.screen, self.config = self._set_mode(config)
        self.internal_surface = pygame.Surface(self.config.internal_size).convert()
        pygame.display.set_caption(window_title())

    def _set_mode(self, config: DisplayConfig) -> tuple[pygame.Surface, DisplayConfig]:
        flags = pygame.FULLSCREEN if config.fullscreen else 0
        try:
            return pygame.display.set_mode(config.window_size, flags), config
        except pygame.error as err:
            fallback_scale = DisplayConfig.SUPPORTED_SCALES[0]
            if config.selected_scale == fallback_scale:
                raise
            LOGGER.warning(
                "set_mode(%s) failed (%s); retrying at scale %s.",
                config.window_size,
                err,
                fallback_scale,
            )
            fb = DisplayConfig(
                internal_width=config.internal_width,
                internal_height=config.internal_height,
                selected_scale=fallback_scale,
                fullscreen=config.fullscreen,
            )
            return pygame.display.set_mode(fb.window_size, flags), fb

    @classmethod
    def create_default(cls) -> "DisplayManager":
        desktop = desktop_size_for_default_scale()
        scale = choose_default_scale(desktop)
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

    def to_render_event(self, event):
        """Translate a window-coordinate pygame event into internal-resolution coords."""
        if not hasattr(event, "pos"):
            return event
        attrs = dict(event.__dict__)
        attrs["pos"] = self.window_to_internal(event.pos)
        return pygame.event.Event(event.type, attrs)

    def apply_config(self, config: DisplayConfig) -> pygame.Surface:
        previous_config = self.config
        previous_screen = self.screen
        previous_internal_surface = self.internal_surface
        try:
            screen, resolved = self._set_mode(config)
        except pygame.error:
            self.config = previous_config
            self.screen = previous_screen
            self.internal_surface = previous_internal_surface
            raise
        self.config = resolved
        self.screen = screen
        self.internal_surface = pygame.Surface(resolved.internal_size).convert()
        pygame.display.set_caption(window_title())
        return self.screen
