"""Banner / status / tooltip drawing routines used by the global message HUD."""

from __future__ import annotations

from typing import Tuple

import pygame

from ui.theme import DEFAULT_THEME, Theme
from ui.widgets import truncate_text_to_px


def draw_banner_bar(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    bar_color: Tuple[int, int, int] = (120, 40, 50),
    theme: Theme = DEFAULT_THEME,
    horizontal_inset: int = 0,
    top: int = 0,
) -> None:
    w = surface.get_width()
    bar_h = 30
    inner_w = max(0, w - 2 * horizontal_inset)
    pygame.draw.rect(surface, bar_color, (horizontal_inset, top, inner_w, bar_h))
    surface.blit(font.render(text, True, theme.text), (horizontal_inset + 10, top + 5))


def draw_global_messages_bottom_dock(
    surface: pygame.Surface,
    banner_font: pygame.font.Font,
    status_font: pygame.font.Font,
    banner_message: str,
    status_message: str,
    horizontal_inset: int,
    theme: Theme = DEFAULT_THEME,
) -> None:
    """Wide horizontal strip at the bottom (between pillar insets)."""
    w, h = surface.get_size()
    inner_w = max(0, w - 2 * horizontal_inset)
    margin = 8
    row_status_h = 22
    row_banner_h = 30
    gap = 2

    if banner_message and status_message:
        total_h = row_status_h + gap + row_banner_h
        y_top = h - margin - total_h
        pygame.draw.rect(
            surface, (32, 36, 48), (horizontal_inset, y_top, inner_w, row_status_h), border_radius=6
        )
        pygame.draw.rect(
            surface,
            (120, 40, 50),
            (horizontal_inset, y_top + row_status_h + gap, inner_w, row_banner_h),
            border_radius=6,
        )
        st = truncate_text_to_px(status_message, status_font, inner_w - 20)
        surface.blit(status_font.render(st, True, (255, 230, 120)), (horizontal_inset + 10, y_top + 4))
        bt = truncate_text_to_px(banner_message, banner_font, inner_w - 20)
        surface.blit(banner_font.render(bt, True, theme.text), (horizontal_inset + 10, y_top + row_status_h + gap + 6))
        return
    if banner_message:
        y = h - margin - row_banner_h
        pygame.draw.rect(surface, (120, 40, 50), (horizontal_inset, y, inner_w, row_banner_h), border_radius=6)
        bt = truncate_text_to_px(banner_message, banner_font, inner_w - 20)
        surface.blit(banner_font.render(bt, True, theme.text), (horizontal_inset + 10, y + 6))
        return
    if status_message:
        row_h = 28
        y = h - margin - row_h
        pygame.draw.rect(surface, (32, 36, 48), (horizontal_inset, y, inner_w, row_h), border_radius=6)
        st = truncate_text_to_px(status_message, status_font, inner_w - 20)
        surface.blit(status_font.render(st, True, (255, 230, 120)), (horizontal_inset + 10, y + 6))


def draw_tooltip(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    pos: Tuple[int, int],
    theme: Theme = DEFAULT_THEME,
) -> None:
    if not text:
        return
    pad = 8
    ren = font.render(text, True, theme.text)
    r = ren.get_rect(topleft=(pos[0] + 14, pos[1] + 14))
    bg = pygame.Rect(r.x - pad, r.y - pad, r.w + 2 * pad, r.h + 2 * pad)
    pygame.draw.rect(surface, (25, 28, 38), bg, border_radius=4)
    pygame.draw.rect(surface, theme.border_focus, bg, width=1, border_radius=4)
    surface.blit(ren, r)
