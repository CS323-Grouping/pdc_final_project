"""Brief \"effect acquired\" toasts top-left on the playable area (below perf overlay when enabled).

Active buff/debuff timers + icons remain on the in-game panel renderer (bottom).
"""

from __future__ import annotations

from typing import Sequence

import pygame

from ui.performance_overlay import playable_area_top_after_performance_bar
from world.constants import PLAYABLE_WIDTH, PLAYABLE_X

# Background ~75% transparent (25% opaque).
_PANEL_ALPHA = 64
_BORDER_ALPHA = 90
_PANEL_BASE = (12, 20, 36)
_BORDER = (72, 120, 170)

_BUFF_TEXT = (150, 215, 255)
_DEBUFF_TEXT = (255, 130, 130)

_MAX_LINES = 5
_LINE_PAD_X = 5
_LINE_PAD_Y = 3
_INNER_GAP = 2


def _truncate(font: pygame.font.Font, text: str, max_w: int) -> str:
    if max_w <= 8:
        return ""
    if font.size(text)[0] <= max_w:
        return text
    ell = "…"
    ts = text
    while ts and font.size(ts + ell)[0] > max_w:
        ts = ts[:-1]
    return ts + ell if ts else ell


def draw_playable_effect_acquire_toasts(
    surface: pygame.Surface,
    font: pygame.font.Font,
    scale: int,
    toast_rows: Sequence[tuple[str, bool]],
    show_performance_metrics: bool,
    perf_overlay_font: pygame.font.Font,
) -> None:
    rows = toast_rows[-_MAX_LINES:]
    if not rows:
        return

    anchor_y = 0
    top = playable_area_top_after_performance_bar(perf_overlay_font, show_performance_metrics, anchor_y)
    left = PLAYABLE_X * scale + 4
    max_panel_w = max(32, PLAYABLE_WIDTH * scale - 8)
    max_line_w = max(8, max_panel_w - 2 * _LINE_PAD_X)

    rendered: list[pygame.Surface] = []
    inner_w = 0
    inner_h = 0
    for text, is_debuff in rows:
        color = _DEBUFF_TEXT if is_debuff else _BUFF_TEXT
        fit = _truncate(font, text, max_line_w)
        surf = font.render(fit, True, color)
        rendered.append(surf)
        inner_w = max(inner_w, surf.get_width())
        inner_h += surf.get_height() + _INNER_GAP
    inner_h -= _INNER_GAP if rendered else 0

    panel_w = min(max_panel_w, _LINE_PAD_X * 2 + inner_w)
    panel_h = _LINE_PAD_Y * 2 + inner_h

    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((*_PANEL_BASE, _PANEL_ALPHA))
    pygame.draw.rect(panel, (*_BORDER, _BORDER_ALPHA), panel.get_rect(), width=1)

    y = _LINE_PAD_Y
    for surf in rendered:
        panel.blit(surf, (_LINE_PAD_X, y))
        y += surf.get_height() + _INNER_GAP

    surface.blit(panel, (left, top))
