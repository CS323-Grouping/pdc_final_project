"""Room-card and roster-row drawing for the LAN room browser."""

from __future__ import annotations

from typing import Literal, Tuple

import pygame

from ui import animations as anim
from ui.theme import DEFAULT_THEME, Theme
from ui.widgets import draw_lock_icon

BadgeKind = Literal["lobby", "starting", "full", "ingame", "paused", "reconnect"]


def badge_color(kind: BadgeKind, theme: Theme = DEFAULT_THEME) -> Tuple[int, int, int]:
    if kind == "lobby":
        return theme.badge_lobby
    if kind == "starting":
        return theme.badge_starting
    if kind == "full":
        return theme.badge_full
    if kind == "paused":
        return theme.badge_starting
    if kind == "reconnect":
        return theme.badge_lobby
    return theme.badge_ingame


def draw_room_card(
    surface: pygame.Surface,
    fonts: Tuple[pygame.font.Font, pygame.font.Font],
    rect: pygame.Rect,
    room_name: str,
    cur: int,
    max_p: int,
    badge_label: str,
    badge_kind: BadgeKind,
    joinable: bool,
    fade: float,
    addr_line: str,
    theme: Theme = DEFAULT_THEME,
) -> None:
    body_font, tiny = fonts
    fade = anim.clamp01(fade)
    alpha = int(255 * fade)

    base = theme.card_joinable if joinable else theme.card_dim
    if not joinable:
        base = tuple(int(c * 0.55) for c in base)

    card = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    card.fill((*base, min(250, alpha)))
    pygame.draw.rect(card, (*theme.border, min(240, alpha)), card.get_rect(), width=1, border_radius=8)

    bx = 10
    by = 8
    chip_c = badge_color(badge_kind, theme)
    pad = body_font.render(f" {badge_label} ", True, (20, 22, 28))
    chip_rect = pygame.Rect(bx, by, pad.get_width() + 10, pad.get_height() + 6)
    pygame.draw.rect(card, (*chip_c, alpha), chip_rect, border_radius=4)
    card.blit(pad, (bx + 5, by + 3))

    title_x = chip_rect.right + 12
    tcol = tuple(min(255, int(c * fade + theme.bg[i] * (1 - fade))) for i, c in enumerate(theme.text))
    title = body_font.render(f"{room_name}  {cur}/{max_p}", True, tcol)
    card.blit(title, (title_x, by + 2))

    if badge_kind in ("ingame", "paused"):
        lock_r = pygame.Rect(rect.w - 38, 8, 22, 26)
        draw_lock_icon(card, lock_r, theme.text_muted)

    sub = tiny.render(addr_line, True, theme.text_muted)
    card.blit(sub, (12, rect.h - 22))

    surface.blit(card, rect.topleft)


def draw_roster_row(
    surface: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    line: str,
    highlight: float,
    theme: Theme = DEFAULT_THEME,
) -> None:
    hl = anim.clamp01(highlight)
    if hl > 0.01:
        glow = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        glow.fill((100, 180, 255, int(50 * hl)))
        surface.blit(glow, rect.topleft)
    pygame.draw.rect(surface, theme.bg_panel, rect, border_radius=4)
    pygame.draw.rect(surface, theme.border, rect, width=1, border_radius=4)
    surface.blit(font.render(line, True, theme.text), (rect.x + 10, rect.y + 8))
