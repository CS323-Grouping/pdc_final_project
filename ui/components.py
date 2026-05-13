from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Optional, Tuple

import pygame

from ui import animations as anim
from ui.theme import DEFAULT_THEME, Theme
from world.assets import WorldAssets
from world.constants import INTERNAL_HEIGHT, INTERNAL_WIDTH
from world.rendering import draw_static_game_frame

BadgeKind = Literal["lobby", "starting", "full", "ingame", "paused", "reconnect"]

# In-game HUD: classify power-up labels for tint (until final UI art lands).
_EFFECT_BUFF_LABELS = frozenset(
    {"Speed Buff", "Jump Buff", "Shield Aura", "Double Jump", "Launch"},
)
_EFFECT_DEBUFF_LABELS = frozenset(
    {"Reverse Control", "Slippery", "Slow Falling", "Heavy", "Weak Jump"},
)


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
    if kind == "paused":
        return theme.badge_starting
    if kind == "reconnect":
        return theme.badge_lobby
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
        st = _truncate_text_to_px(status_message, status_font, inner_w - 20)
        surface.blit(status_font.render(st, True, (255, 230, 120)), (horizontal_inset + 10, y_top + 4))
        bt = _truncate_text_to_px(banner_message, banner_font, inner_w - 20)
        surface.blit(banner_font.render(bt, True, theme.text), (horizontal_inset + 10, y_top + row_status_h + gap + 6))
        return
    if banner_message:
        y = h - margin - row_banner_h
        pygame.draw.rect(surface, (120, 40, 50), (horizontal_inset, y, inner_w, row_banner_h), border_radius=6)
        bt = _truncate_text_to_px(banner_message, banner_font, inner_w - 20)
        surface.blit(banner_font.render(bt, True, theme.text), (horizontal_inset + 10, y + 6))
        return
    if status_message:
        row_h = 28
        y = h - margin - row_h
        pygame.draw.rect(surface, (32, 36, 48), (horizontal_inset, y, inner_w, row_h), border_radius=6)
        st = _truncate_text_to_px(status_message, status_font, inner_w - 20)
        surface.blit(status_font.render(st, True, (255, 230, 120)), (horizontal_inset + 10, y + 6))


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


def _truncate_text_to_px(text: str, font: pygame.font.Font, max_width: int) -> str:
    if max_width <= 12 or font.size(text)[0] <= max_width:
        return text
    ell = "…"
    t = text
    while len(t) > 1 and font.size(t + ell)[0] > max_width:
        t = t[:-1]
    return t + ell if t != text else text


def _effect_row_color(label: str, theme: Theme) -> Tuple[int, int, int]:
    if label in _EFFECT_BUFF_LABELS:
        return (170, 210, 255)
    if label in _EFFECT_DEBUFF_LABELS:
        return theme.text_warn
    return theme.text


def _format_match_clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m = int(seconds // 60)
    s = seconds % 60.0
    if m > 0:
        return f"{m}:{s:04.1f}"
    return f"{s:.1f}s"


def _draw_ingame_status_hud_top_right(
    surface: pygame.Surface,
    font: pygame.font.Font,
    elimination_lines: list[str],
    effect_timers: Mapping[str, float],
    theme: Theme,
    max_feed_lines: int,
    margin_x: int,
    margin_y: int,
    max_panel_width: int,
    align_right: bool,
    edge_inset: int,
    match_elapsed_sec: float | None,
    platforms_reached: int | None,
) -> None:
    feed_visible = [ln for ln in elimination_lines[-max_feed_lines:] if ln.strip()]
    effects = [(n, t) for n, t in effect_timers.items() if t > 0]
    show_metrics = match_elapsed_sec is not None or platforms_reached is not None
    if not feed_visible and not effects and not show_metrics:
        return

    pad = 14
    line_gap = 4
    section_gap = 10
    line_h = max(font.get_linesize(), 18)

    inner_w_min = 220
    tw_feed = max((font.size(line)[0] for line in feed_visible), default=0)
    tw_effects = 0
    for name, rem in effects:
        label_w = font.size(name)[0]
        time_w = font.size(f"{rem:.1f}s")[0]
        tw_effects = max(tw_effects, label_w + 12 + time_w)

    tw_metrics = 0
    if show_metrics:
        if match_elapsed_sec is not None:
            tw_metrics = max(tw_metrics, font.size(f"Time  {_format_match_clock(match_elapsed_sec)}")[0])
        if platforms_reached is not None:
            tw_metrics = max(tw_metrics, font.size(f"Platforms  {platforms_reached}")[0])

    panel_content_w = max(inner_w_min, tw_feed, tw_effects, tw_metrics)
    panel_w = min(max_panel_width, pad * 2 + panel_content_w)
    inner_w = panel_w - 2 * pad

    header_h = line_h + 3
    metrics_h = 0
    if show_metrics:
        nlines = (1 if match_elapsed_sec is not None else 0) + (1 if platforms_reached is not None else 0)
        metrics_h = header_h + nlines * (line_h + line_gap) - line_gap

    if feed_visible:
        feed_lines_h = len(feed_visible) * (line_h + line_gap) - line_gap
        feed_block_h = header_h + feed_lines_h
    else:
        feed_block_h = 0

    has_mid_div = show_metrics and (feed_visible or effects)
    divider_after_metrics = (section_gap + 1 + section_gap) if has_mid_div else 0

    has_both = bool(feed_visible) and bool(effects)
    divider_feed_effects = (section_gap + 1 + section_gap) if has_both else 0

    if effects:
        eff_lines_h = len(effects) * (line_h + line_gap) - line_gap
        effects_block_h = header_h + eff_lines_h
    else:
        effects_block_h = 0

    panel_h = pad + metrics_h + divider_after_metrics + feed_block_h + divider_feed_effects + effects_block_h + pad
    sw = surface.get_width()
    if align_right:
        panel_x = sw - edge_inset - panel_w
    else:
        panel_x = margin_x
    panel = pygame.Rect(panel_x, margin_y, panel_w, panel_h)

    bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
    bg.fill((*theme.bg_panel, 240))
    surface.blit(bg, panel.topleft)
    pygame.draw.rect(surface, theme.border, panel, width=1, border_radius=10)

    y = panel.y + pad
    x_text = panel.x + pad
    text_bright = (232, 238, 248)

    if show_metrics:
        cap = font.render("MATCH", True, theme.text_muted)
        surface.blit(cap, (x_text, y))
        y += header_h
        if match_elapsed_sec is not None:
            line = f"Time  {_format_match_clock(match_elapsed_sec)}"
            surface.blit(font.render(line, True, text_bright), (x_text, y))
            y += line_h + line_gap
        if platforms_reached is not None:
            surface.blit(
                font.render(f"Platforms  {platforms_reached}", True, text_bright),
                (x_text, y),
            )
            y += line_h + line_gap

    if has_mid_div:
        div_y = y + section_gap // 2
        pygame.draw.line(surface, theme.border, (x_text, div_y), (panel.right - pad, div_y), 1)
        y = div_y + 1 + section_gap

    if feed_visible:
        cap = font.render("RACE FEED", True, theme.text_muted)
        surface.blit(cap, (x_text, y))
        y += header_h
        for line in feed_visible:
            msg = _truncate_text_to_px(line, font, inner_w)
            surface.blit(font.render(msg, True, text_bright), (x_text, y))
            y += line_h + line_gap

    if has_both:
        div_y = y + section_gap // 2
        pygame.draw.line(surface, theme.border, (x_text, div_y), (panel.right - pad, div_y), 1)
        y = div_y + 1 + section_gap

    if effects:
        cap = font.render("YOUR EFFECTS", True, theme.text_muted)
        surface.blit(cap, (x_text, y))
        y += header_h
        for name, remaining in effects:
            col = _effect_row_color(name, theme)
            time_s = f"{remaining:.1f}s"
            name_px = max(40, inner_w - font.size(time_s)[0] - 10)
            name_shown = _truncate_text_to_px(name, font, name_px)
            tw = font.size(time_s)[0]
            surface.blit(font.render(name_shown, True, col), (x_text, y))
            surface.blit(font.render(time_s, True, col), (panel.right - pad - tw, y))
            y += line_h + line_gap


def _draw_ingame_status_hud_bottom_bar(
    surface: pygame.Surface,
    font: pygame.font.Font,
    elimination_lines: list[str],
    effect_timers: Mapping[str, float],
    theme: Theme,
    max_feed_lines: int,
    edge_inset: int,
    bottom_margin: int,
    match_elapsed_sec: float | None,
    platforms_reached: int | None,
) -> None:
    feed_visible = [ln for ln in elimination_lines[-max_feed_lines:] if ln.strip()]
    effects = [(n, t) for n, t in effect_timers.items() if t > 0]
    show_metrics = match_elapsed_sec is not None or platforms_reached is not None
    if not feed_visible and not effects and not show_metrics:
        return

    sw, sh = surface.get_size()
    inner_w = max(0, sw - 2 * edge_inset)
    pad_x = 10
    pad_y = 6
    text_bright = (232, 238, 248)

    parts: list[str] = []
    if show_metrics:
        bits = []
        if match_elapsed_sec is not None:
            bits.append(f"Time {_format_match_clock(match_elapsed_sec)}")
        if platforms_reached is not None:
            bits.append(f"Platforms {platforms_reached}")
        if bits:
            parts.append("MATCH  " + " · ".join(bits))
    if feed_visible:
        parts.append("RACE  " + " · ".join(ln.strip() for ln in feed_visible))
    if effects:
        parts.append("FX  " + " · ".join(f"{n} {t:.1f}s" for n, t in effects))

    sep = "   │   "
    line = sep.join(parts)
    max_text_w = max(40, inner_w - 2 * pad_x)
    line = _truncate_text_to_px(line, font, max_text_w)

    line_h = max(font.get_linesize(), 16)
    bar_h = pad_y * 2 + line_h
    panel = pygame.Rect(edge_inset, sh - bottom_margin - bar_h, inner_w, bar_h)

    bg = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
    bg.fill((*theme.bg_panel, 230))
    surface.blit(bg, panel.topleft)
    pygame.draw.rect(surface, theme.border, panel, width=1, border_radius=10)

    ty = panel.y + pad_y
    surface.blit(font.render(line, True, text_bright), (panel.x + pad_x, ty))


def draw_ingame_status_hud(
    surface: pygame.Surface,
    font: pygame.font.Font,
    elimination_lines: list[str],
    effect_timers: Mapping[str, float],
    theme: Theme = DEFAULT_THEME,
    max_feed_lines: int = 6,
    margin_x: int = 12,
    margin_y: int = 12,
    max_panel_width: int = 380,
    align_right: bool = True,
    edge_inset: int = 18,
    match_elapsed_sec: float | None = None,
    platforms_reached: int | None = None,
    layout: Literal["bottom_bar", "top_right"] = "bottom_bar",
    bottom_margin: int = 8,
) -> None:
    """
    Match metrics, elimination feed, and power-up timers.
    Default `layout="bottom_bar"`: one horizontal strip above the window bottom (between pillar insets).
    """
    if layout == "top_right":
        _draw_ingame_status_hud_top_right(
            surface,
            font,
            elimination_lines,
            effect_timers,
            theme,
            max_feed_lines,
            margin_x,
            margin_y,
            max_panel_width,
            align_right,
            edge_inset,
            match_elapsed_sec,
            platforms_reached,
        )
        return
    _draw_ingame_status_hud_bottom_bar(
        surface,
        font,
        elimination_lines,
        effect_timers,
        theme,
        max_feed_lines,
        edge_inset,
        bottom_margin,
        match_elapsed_sec,
        platforms_reached,
    )


def draw_elimination_feed(
    surface: pygame.Surface,
    font: pygame.font.Font,
    lines: list[str],
    theme: Theme = DEFAULT_THEME,
    max_lines: int = 6,
) -> None:
    draw_ingame_status_hud(
        surface,
        font,
        lines,
        {},
        theme=theme,
        max_feed_lines=max_lines,
    )


# --- Match results (dungeon board style) -------------------------------------------

_BRICK_BASE = (38, 44, 58)
_TORCH_WOOD = (85, 55, 35)
_PANEL_FILL = (22, 28, 46)
_PANEL_OUTER = (95, 105, 135)
_PANEL_INNER = (55, 65, 88)
_GOLD = (230, 190, 72)
_GOLD_DIM = (180, 145, 55)
_BRONZE = (168, 110, 62)
_SILVER = (150, 160, 176)
_TITLE_BLUE = (150, 200, 255)


def _draw_stone_wall(surface: pygame.Surface, w: int, h: int) -> None:
    bw, bh = 52, 26
    for yy in range(0, h + bh, bh):
        row = (yy // bh) % 2
        for xx in range(-bw, w + bw, bw):
            x = xx + (row * (bw // 2))
            jitter = ((xx // bw + yy // bh) * 17) % 9
            base = 36 + jitter
            c = (base, base + 3, base + 8)
            r = pygame.Rect(x, yy, bw - 3, bh - 3)
            pygame.draw.rect(surface, c, r)
            pygame.draw.rect(surface, (24, 28, 38), r, width=1)


def _draw_side_torches(surface: pygame.Surface, w: int, h: int) -> None:
    for side_x in (18, w - 36):
        pygame.draw.rect(surface, _TORCH_WOOD, pygame.Rect(side_x, h // 2 - 40, 14, 80), border_radius=2)
        flame = pygame.Rect(side_x - 4, h // 2 - 52, 22, 28)
        pygame.draw.ellipse(surface, (200, 90, 30), flame)
        pygame.draw.ellipse(surface, (255, 200, 80), flame.inflate(-6, -8))


def _draw_hanging_banners(surface: pygame.Surface, w: int) -> None:
    for x in (40, w - 56):
        pygame.draw.rect(surface, (28, 38, 72), pygame.Rect(x, 8, 28, 44))
        pygame.draw.polygon(surface, (22, 32, 62), [(x, 52), (x + 14, 72), (x + 28, 52)])


def _draw_corner_rivets(surface: pygame.Surface, rect: pygame.Rect) -> None:
    pts = [
        (rect.left + 10, rect.top + 10),
        (rect.right - 10, rect.top + 10),
        (rect.left + 10, rect.bottom - 10),
        (rect.right - 10, rect.bottom - 10),
    ]
    for cx, cy in pts:
        pygame.draw.circle(surface, (130, 136, 150), (cx, cy), 5)
        pygame.draw.circle(surface, (75, 80, 95), (cx, cy), 5, width=1)
        pygame.draw.circle(surface, (160, 168, 180), (cx - 1, cy - 1), 2)


def _winner_badge_top_font(detail_f: pygame.font.Font) -> pygame.font.Font:
    sz = max(8, min(11, detail_f.get_height() - 4))
    return pygame.font.SysFont(DEFAULT_THEME.font_body, sz)


def _draw_mini_crown(surface: pygame.Surface, cx: int, cy: int, color: Tuple[int, int, int]) -> None:
    pts = [(cx - 10, cy + 4), (cx - 6, cy - 4), (cx - 2, cy + 2), (cx + 2, cy - 4), (cx + 6, cy + 2), (cx + 10, cy + 4)]
    pygame.draw.lines(surface, color, False, pts, 3)
    pygame.draw.line(surface, color, (cx - 10, cy + 4), (cx + 10, cy + 4), 2)


def _fmt_time_played(cs: int) -> str:
    if cs <= 0:
        return "—"
    total = cs / 100.0
    m = int(total // 60)
    s = int(round(total - m * 60))
    if s >= 60:
        m += 1
        s = 0
    return f"{m:02d}m {s:02d}s"


def _rank_badge_label(placement: int) -> str:
    if placement == 255:
        return "—"
    if placement == 1:
        return "1ST"
    if placement == 2:
        return "2ND"
    if placement == 3:
        return "3RD"
    if placement == 4:
        return "4TH"
    return f"{placement}TH"


def _placeholder_avatar(size: int) -> pygame.Surface:
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(s, (55, 62, 78), s.get_rect(), border_radius=size // 6)
    pygame.draw.circle(s, (120, 130, 148), (size // 2, size // 2 - 2), size // 5)
    pygame.draw.rect(s, (120, 130, 148), pygame.Rect(size // 2 - size // 5, size // 2 + 2, size * 2 // 5, size // 4), border_radius=2)
    return s


def draw_results_table(
    surface: pygame.Surface,
    fonts: Tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
    standings: list[tuple],
    elapsed: float,
    placement_label_fn: Callable[[int], str],
    theme: Theme = DEFAULT_THEME,
    local_player_id: Optional[int] = None,
    local_avatar: Optional[pygame.Surface] = None,
    world_assets: Optional[WorldAssets] = None,
    footer_reserve_extra: int = 0,
    remote_avatars: Optional[dict] = None,
) -> Tuple[int, int]:
    """
    Standings rows: (player_id, placement, name) or extended (…, elapsed_centisec, platforms).
    fonts: (title_font, name_column_font, detail_font)

    The level backdrop is rendered at internal resolution (320×180) and scaled to the surface;
    UI is drawn at the surface's native resolution.
    """
    title_f, name_f, detail_f = fonts
    rows = sorted(standings, key=lambda row: row[1])
    w, h = surface.get_size()

    if world_assets is not None:
        ib = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
        draw_static_game_frame(ib, world_assets, camera_y=0.0)
        pygame.transform.scale(ib, (w, h), surface)
    else:
        ib = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
        _draw_stone_wall(ib, INTERNAL_WIDTH, INTERNAL_HEIGHT)
        _draw_hanging_banners(ib, INTERNAL_WIDTH)
        _draw_side_torches(ib, INTERNAL_WIDTH, INTERNAL_HEIGHT)
        pygame.transform.scale(ib, (w, h), surface)

    title_s = title_f.render("MATCH RESULTS", True, _TITLE_BLUE)
    title_h = title_s.get_height()
    title_gap = max(8, min(14, h // 14))
    footer_reserve = 28 + max(0, footer_reserve_extra)

    pw = min(760, w - 16)
    nrows = len(rows)
    max_panel_h = max(60, h - footer_reserve - title_h - title_gap - 10)
    top_bottom = 12
    header_h = min(34, max(24, max_panel_h // (max(4, nrows + 2))))
    inner_pad_bottom = 16
    row_h = max(34, min(56, (max_panel_h - top_bottom - header_h - inner_pad_bottom) // max(1, nrows)))
    panel_h = top_bottom + header_h + nrows * row_h + inner_pad_bottom
    if panel_h > max_panel_h:
        row_h = max(30, (max_panel_h - top_bottom - header_h - inner_pad_bottom) // max(1, nrows))
        panel_h = top_bottom + header_h + nrows * row_h + inner_pad_bottom

    block_h = title_h + title_gap + panel_h
    top = max(6, (h - block_h - footer_reserve) // 2)
    surface.blit(title_s, title_s.get_rect(midtop=(w // 2, top)))
    panel = pygame.Rect((w - pw) // 2, top + title_h + title_gap, pw, panel_h)
    pygame.draw.rect(surface, _PANEL_FILL, panel, border_radius=6)
    pygame.draw.rect(surface, _PANEL_OUTER, panel, width=3, border_radius=6)
    pygame.draw.rect(surface, _PANEL_INNER, panel.inflate(-12, -12), width=1, border_radius=4)
    _draw_corner_rivets(surface, panel)

    # Column layout: name grows; time & platforms are fixed-width and right-aligned.
    inner = panel.inflate(-12, -26)
    iy = inner.y + 6
    pad_inner = 8
    content_right = inner.right - pad_inner

    col_plat_w = 44
    col_gap = 10
    col_time_w = 86
    col_badge = 58
    col_av = 36
    gap_after_av = 8

    for _ in range(6):
        content_left = inner.x + pad_inner
        right_plat = content_right
        left_plat = right_plat - col_plat_w
        right_time = left_plat - col_gap
        left_time = right_time - col_time_w
        x_av = content_left + col_badge
        x_name = x_av + col_av + gap_after_av
        name_max_w = left_time - x_name - 10
        if name_max_w >= 34:
            break
        col_time_w = max(62, col_time_w - 6)
        col_badge = max(46, col_badge - 4)
        col_av = max(30, col_av - 2)
        col_plat_w = max(32, col_plat_w - 2)
        col_gap = max(6, col_gap - 1)

    name_max_w = max(20, name_max_w)

    narrow = inner.w < 258
    sep_col = detail_f.render("◆", True, (80, 120, 180))
    hdr_y = iy + 6
    h_name = detail_f.render("NAME", True, theme.text_muted)
    time_hdr = "TIME" if narrow else "TIME PLAYED"
    plat_hdr = "PLAT" if narrow else "PLATFORMS"
    h_time = detail_f.render(time_hdr, True, theme.text_muted)
    h_plat = detail_f.render(plat_hdr, True, theme.text_muted)
    surface.blit(h_name, (x_name, hdr_y))
    sep1x = left_time - 14 - sep_col.get_width() // 2
    surface.blit(sep_col, (sep1x, hdr_y))
    surface.blit(h_time, (right_time - h_time.get_width(), hdr_y))
    sep2x = left_plat - 14 - sep_col.get_width() // 2
    surface.blit(sep_col, (sep2x, hdr_y))
    surface.blit(h_plat, (right_plat - h_plat.get_width(), hdr_y))
    hdr_rule_y = hdr_y + max(24, header_h - 10)
    pygame.draw.line(surface, _PANEL_INNER, (inner.x, hdr_rule_y), (inner.right, hdr_rule_y), 1)

    av_size = 42
    plat_local = local_avatar
    y = hdr_y + header_h
    win_label_f = _winner_badge_top_font(detail_f)
    for i, row in enumerate(rows):
        alpha = anim.stagger_alpha(elapsed, i)
        if alpha < 0.02:
            continue
        if len(row) >= 5:
            player_id, placement, name, elapsed_cs, platforms = row[:5]
        else:
            player_id, placement, name = row[:3]
            elapsed_cs, platforms = 0, 0

        is_winner = placement == 1
        row_rect = pygame.Rect(inner.x + 4, y - 2, inner.w - 8, row_h - 4)

        if is_winner:
            glow = pygame.Surface(row_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*_GOLD, int(55 * alpha)), glow.get_rect(), border_radius=8)
            surface.blit(glow, row_rect.topleft)
            pygame.draw.rect(surface, _GOLD, row_rect, width=2, border_radius=8)

        badge_rect = pygame.Rect(content_left + 6, y + 5, col_badge - 12, row_h - 10)
        badge_txt = _rank_badge_label(placement)
        if placement == 255:
            bcol, bborder = (70, 78, 95), (100, 110, 125)
        elif is_winner:
            bcol, bborder = (40, 35, 22), _GOLD
        elif placement == 3:
            bcol, bborder = (45, 32, 24), _BRONZE
        else:
            bcol, bborder = (38, 42, 55), _SILVER

        pygame.draw.rect(surface, bcol, badge_rect, border_radius=4)
        pygame.draw.rect(surface, bborder, badge_rect, width=2, border_radius=4)
        if is_winner:
            win_top = win_label_f.render(placement_label_fn(1).upper(), True, _GOLD)
            win_bot = detail_f.render(badge_txt, True, _GOLD)
            v_gap = 2
            total_h = win_top.get_height() + v_gap + win_bot.get_height()
            ty = min(badge_rect.bottom - total_h - 2, badge_rect.centery - total_h // 2)
            ty = max(badge_rect.top + 2, ty)
            surface.blit(win_top, (badge_rect.centerx - win_top.get_width() // 2, ty))
            surface.blit(
                win_bot,
                (badge_rect.centerx - win_bot.get_width() // 2, ty + win_top.get_height() + v_gap),
            )
            crown_x = max(content_left, badge_rect.right + 4)
            _draw_mini_crown(surface, crown_x + 10, badge_rect.centery, _GOLD)
        else:
            bt = detail_f.render(badge_txt, True, theme.text)
            surface.blit(bt, bt.get_rect(center=badge_rect.center))

        av_x = x_av + 4
        av_y = y + (row_h - av_size) // 2
        avatar_source: Optional[pygame.Surface] = None
        if local_player_id is not None and player_id == local_player_id:
            avatar_source = plat_local
        elif remote_avatars is not None:
            avatar_source = remote_avatars.get(player_id)
        if avatar_source is not None:
            scaled = pygame.transform.smoothscale(avatar_source, (av_size, av_size))
            surface.blit(scaled, (av_x, av_y))
            pygame.draw.rect(surface, _PANEL_OUTER, pygame.Rect(av_x, av_y, av_size, av_size), width=1, border_radius=6)
        else:
            ph = _placeholder_avatar(av_size)
            surface.blit(ph, (av_x, av_y))

        nm = _truncate_text_to_px((name or "")[:48], name_f, name_max_w)
        name_col = tuple(int(c * alpha + _PANEL_FILL[i] * (1 - alpha)) for i, c in enumerate((_GOLD if is_winner else theme.text)[:3]))
        name_surf = name_f.render(nm, True, name_col)
        surface.blit(name_surf, (x_name, y + (row_h - name_surf.get_height()) // 2))

        t_str = _fmt_time_played(int(elapsed_cs))
        t_col = tuple(int(c * alpha + _PANEL_FILL[i] * (1 - alpha)) for i, c in enumerate((_GOLD if is_winner else theme.text)[:3]))
        time_s = detail_f.render(t_str, True, t_col)
        surface.blit(time_s, (right_time - time_s.get_width(), y + (row_h - time_s.get_height()) // 2))

        p_str = "—" if placement == 255 else str(int(platforms))
        p_col = tuple(int(c * alpha + _PANEL_FILL[i] * (1 - alpha)) for i, c in enumerate((_GOLD if is_winner else theme.text)[:3]))
        plat_s = detail_f.render(p_str, True, p_col)
        surface.blit(plat_s, (right_plat - plat_s.get_width(), y + (row_h - plat_s.get_height()) // 2))

        pygame.draw.line(surface, (45, 52, 68), (inner.x, y + row_h - 2), (inner.right, y + row_h - 2), 1)
        y += row_h

    return y, len(rows)
