from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional, Tuple

import pygame

from ui import animations as anim
from ui.theme import DEFAULT_THEME, Theme

BadgeKind = Literal["lobby", "starting", "full", "ingame"]


@dataclass
class Button:
    rect: pygame.Rect
    text: str
    enabled: bool = True


def draw_button(
    surface: pygame.Surface,
    font: pygame.font.Font,
    btn: Button,
    theme: Theme = DEFAULT_THEME,
    hovered: bool = False,
    variant: Literal["primary", "danger", "neutral"] = "primary",
) -> None:
    if variant == "danger":
        base = theme.danger if btn.enabled else theme.accent_disabled
        hi = theme.danger_hover
    elif variant == "neutral":
        base = theme.bg_panel if btn.enabled else theme.accent_disabled
        hi = theme.border_focus
    else:
        base = theme.accent if btn.enabled else theme.accent_disabled
        hi = theme.accent_hover

    fill = hi if (hovered and btn.enabled) else base
    pygame.draw.rect(surface, fill, btn.rect, border_radius=6)
    border_c = theme.border if btn.enabled else (55, 55, 65)
    pygame.draw.rect(surface, border_c, btn.rect, width=2, border_radius=6)
    tc = theme.text if btn.enabled else theme.text_muted
    label = font.render(btn.text, True, tc)
    surface.blit(label, label.get_rect(center=btn.rect.center))


@dataclass
class TextInput:
    rect: pygame.Rect
    label: str
    value: str
    focused: bool


def draw_text_input(
    surface: pygame.Surface,
    fonts: Tuple[pygame.font.Font, pygame.font.Font],
    inp: TextInput,
    theme: Theme = DEFAULT_THEME,
) -> None:
    body, hint = fonts
    cap = body.render(inp.label, True, theme.text_muted)
    surface.blit(cap, (inp.rect.x, inp.rect.y - 22))
    pygame.draw.rect(surface, theme.bg_input, inp.rect, border_radius=6)
    bc = theme.border_focus if inp.focused else theme.border
    pygame.draw.rect(surface, bc, inp.rect, width=2, border_radius=6)
    surface.blit(body.render(inp.value, True, theme.text), (inp.rect.x + 10, inp.rect.y + (inp.rect.height - body.get_height()) // 2))


def badge_color(kind: BadgeKind, theme: Theme = DEFAULT_THEME) -> Tuple[int, int, int]:
    if kind == "lobby":
        return theme.badge_lobby
    if kind == "starting":
        return theme.badge_starting
    if kind == "full":
        return theme.badge_full
    return theme.badge_ingame


def draw_lock_icon(surface: pygame.Surface, rect: pygame.Rect, color: Tuple[int, int, int]) -> None:
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    sh = max(3, h // 4)
    body = pygame.Rect(x + w // 4, y + sh, w // 2, h - sh)
    arch_w = w // 2 + 4
    arch = pygame.Rect(x + (w - arch_w) // 2, y, arch_w, sh + 4)
    pygame.draw.rect(surface, color, body, border_radius=3)
    pygame.draw.arc(surface, color, arch, 3.14159, 6.28318, 3)


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

    if badge_kind == "ingame":
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


@dataclass
class ConfirmDialog:
    title: str
    message: str
    on_confirm: Callable[[], None]
    on_cancel: Callable[[], None]
    confirm_label: str = "Yes"
    cancel_label: str = "No"

    def layout(self, screen_w: int, screen_h: int) -> Tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        box = pygame.Rect(0, 0, min(420, screen_w - 48), 160)
        box.center = (screen_w // 2, screen_h // 2)
        yes = pygame.Rect(box.centerx - 110, box.bottom - 48, 100, 38)
        no = pygame.Rect(box.centerx + 10, box.bottom - 48, 100, 38)
        return box, yes, no

    def draw(
        self,
        surface: pygame.Surface,
        fonts: Tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
        theme: Theme = DEFAULT_THEME,
    ) -> Tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        w, h = surface.get_size()
        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill(theme.overlay_scrim)
        surface.blit(scrim, (0, 0))

        title_f, body_f, small_f = fonts
        box, yes_r, no_r = self.layout(w, h)
        pygame.draw.rect(surface, theme.bg_panel, box, border_radius=10)
        pygame.draw.rect(surface, theme.border, box, width=2, border_radius=10)
        surface.blit(title_f.render(self.title, True, theme.text), (box.x + 16, box.y + 14))
        surface.blit(body_f.render(self.message, True, theme.text_muted), (box.x + 16, box.y + 52))

        yes_btn = Button(yes_r, self.confirm_label, True)
        no_btn = Button(no_r, self.cancel_label, True)
        draw_button(surface, small_f, yes_btn, theme, variant="danger")
        draw_button(surface, small_f, no_btn, theme, variant="neutral")
        return box, yes_r, no_r

    def handle_click(self, pos: Tuple[int, int], yes_r: pygame.Rect, no_r: pygame.Rect) -> bool:
        if yes_r.collidepoint(pos):
            self.on_confirm()
            return True
        if no_r.collidepoint(pos):
            self.on_cancel()
            return True
        return False


def draw_banner_bar(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    bar_color: Tuple[int, int, int] = (120, 40, 50),
    theme: Theme = DEFAULT_THEME,
) -> None:
    w = surface.get_width()
    pygame.draw.rect(surface, bar_color, (0, 0, w, 30))
    surface.blit(font.render(text, True, theme.text), (10, 5))


def draw_countdown_overlay(
    surface: pygame.Surface,
    font_large: pygame.font.Font,
    font_small: pygame.font.Font,
    seconds: int,
    pulse_t: float,
    theme: Theme = DEFAULT_THEME,
) -> None:
    w, h = surface.get_size()
    scale = 0.92 + 0.08 * anim.pulse01(pulse_t, 0.75)
    msg = str(max(0, seconds))
    ren = font_large.render(msg, True, theme.badge_starting)
    ren = pygame.transform.smoothscale(ren, (max(1, int(ren.get_width() * scale)), max(1, int(ren.get_height() * scale))))
    surface.blit(ren, ren.get_rect(center=(w // 2, 72)))
    hint = font_small.render("Get ready…", True, theme.text_muted)
    surface.blit(hint, hint.get_rect(center=(w // 2, 120)))


def draw_elimination_feed(
    surface: pygame.Surface,
    font: pygame.font.Font,
    lines: list[str],
    theme: Theme = DEFAULT_THEME,
    max_lines: int = 6,
) -> None:
    if not lines:
        return
    panel_w = 280
    panel_h = 22 * min(len(lines), max_lines) + 16
    panel = pygame.Rect(10, 10, panel_w, panel_h)
    bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
    bg.fill((*theme.bg_panel, 210))
    surface.blit(bg, panel.topleft)
    pygame.draw.rect(surface, theme.border, panel, width=1, border_radius=6)
    y = panel.y + 10
    for line in lines[-max_lines:]:
        surface.blit(font.render(line, True, (200, 220, 255)), (panel.x + 10, y))
        y += 20


def draw_results_table(
    surface: pygame.Surface,
    fonts: Tuple[pygame.font.Font, pygame.font.Font],
    standings: list[tuple[int, int, str]],
    elapsed: float,
    placement_label_fn: Callable[[int], str],
    theme: Theme = DEFAULT_THEME,
) -> Tuple[int, int]:
    """Returns (y_end, rows_drawn)."""
    title_f, row_f = fonts
    rows = sorted(standings, key=lambda row: row[1])
    y = 140
    for i, (_pid, placement, name) in enumerate(rows):
        alpha = anim.stagger_alpha(elapsed, i)
        if alpha < 0.02:
            continue
        line = f"  {placement}.  {name}  —  {placement_label_fn(placement)}"
        col = tuple(int(c * alpha + theme.bg[0] * (1 - alpha)) for c in theme.text[:3])
        surface.blit(row_f.render(line, True, col), (80, y))
        y += 32
    return y, len(rows)
