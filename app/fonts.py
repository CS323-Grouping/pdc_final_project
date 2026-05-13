"""Bundled UI font with system-font fallback (see ``BUNDLED_UI_FONT_FILENAME``)."""

from __future__ import annotations

from pathlib import Path

import pygame

from ui.theme import DEFAULT_THEME

# -----------------------------------------------------------------------------
# Swap the game's UI typeface by editing this one line only. File must live
# under ``assets/font/`` in the repo; PyInstaller bundles all of ``assets/``.
BUNDLED_UI_FONT_FILENAME = "CozetteVector.ttf"
# -----------------------------------------------------------------------------


def bundled_ui_font_path(resource_root: Path) -> Path:
    return resource_root / "assets" / "font" / BUNDLED_UI_FONT_FILENAME


def load_ui_font(
    resource_root: Path,
    size: int,
    *,
    bold: bool = False,
    fallback_family: str | None = None,
) -> pygame.font.Font:
    """Load the bundled UI font when present; otherwise use a system font."""
    px = max(1, int(size))
    path = bundled_ui_font_path(resource_root)
    if path.is_file():
        try:
            font = pygame.font.Font(str(path), px)
            font.set_bold(bold)
            return font
        except pygame.error:
            pass
    fb = fallback_family or DEFAULT_THEME.font_body
    return pygame.font.SysFont(fb, px, bold=bold)
