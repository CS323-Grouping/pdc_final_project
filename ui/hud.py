"""In-game HUD: countdown overlay, status panel (match/race/effects), elimination feed."""

from __future__ import annotations

from typing import Literal, Mapping, Tuple

import pygame

from ui import animations as anim
from ui.theme import DEFAULT_THEME, Theme
from ui.widgets import truncate_text_to_px


# Classify power-up labels for tint (until final UI art lands).
_EFFECT_BUFF_LABELS = frozenset(
    {"Speed Buff", "Jump Buff", "Shield Aura", "Double Jump", "Launch Boost"},
)
_EFFECT_DEBUFF_LABELS = frozenset(
    {"Reverse Control", "Slippery", "Slow Falling", "Heavy", "Weak Jump"},
)


def draw_countdown_overlay(
    surface: pygame.Surface,
    font_large: pygame.font.Font,
    font_small: pygame.font.Font,
    seconds: int,
    pulse_t: float,
    theme: Theme = DEFAULT_THEME,
) -> None:
    w, _h = surface.get_size()
    scale = 0.92 + 0.08 * anim.pulse01(pulse_t, 0.75)
    msg = str(max(0, seconds))
    ren = font_large.render(msg, True, theme.badge_starting)
    ren = pygame.transform.smoothscale(ren, (max(1, int(ren.get_width() * scale)), max(1, int(ren.get_height() * scale))))
    surface.blit(ren, ren.get_rect(center=(w // 2, 72)))
    hint = font_small.render("Get ready…", True, theme.text_muted)
    surface.blit(hint, hint.get_rect(center=(w // 2, 120)))


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
            msg = truncate_text_to_px(line, font, inner_w)
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
            name_shown = truncate_text_to_px(name, font, name_px)
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
    line = truncate_text_to_px(line, font, max_text_w)

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
    Default ``layout="bottom_bar"``: one horizontal strip above the window bottom.
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
