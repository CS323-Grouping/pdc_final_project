"""
Procedural pixel-style UI chrome (no image assets).

Use for modal panels, settings, and temporary screens until art is ready.
Drawing is integer-rect based (no rounded corners) so it matches bitmap fonts
and sprite UI. Import :class:`PixelChromeStyle` / :data:`DEFAULT_PIXEL_STYLE`
and the ``draw_*`` helpers from feature code.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class PixelChromeStyle:
    scrim: tuple[int, int, int, int] = (10, 12, 24, 230)
    frame_rim: tuple[int, int, int] = (140, 200, 255)
    frame_groove: tuple[int, int, int] = (18, 28, 48)
    panel_face: tuple[int, int, int] = (26, 36, 56)
    well_face: tuple[int, int, int] = (16, 22, 36)
    well_border: tuple[int, int, int] = (44, 64, 92)
    drop_face: tuple[int, int, int] = (12, 18, 32)
    drop_border: tuple[int, int, int] = (58, 100, 150)
    arrow_pad_face: tuple[int, int, int] = (24, 34, 52)
    option_sel: tuple[int, int, int] = (32, 88, 150)
    option_sep: tuple[int, int, int] = (40, 60, 86)
    togg_on_face: tuple[int, int, int] = (30, 100, 174)
    togg_on_border: tuple[int, int, int] = (120, 200, 255)
    togg_off_face: tuple[int, int, int] = (40, 44, 56)
    togg_off_border: tuple[int, int, int] = (70, 78, 96)
    knob: tuple[int, int, int] = (238, 246, 255)
    hover_outline: tuple[int, int, int] = (255, 226, 120)
    btn_primary_face: tuple[int, int, int] = (34, 110, 185)
    btn_primary_border: tuple[int, int, int] = (150, 210, 255)
    btn_neutral_face: tuple[int, int, int] = (52, 56, 68)
    btn_neutral_border: tuple[int, int, int] = (120, 126, 140)
    text_title: tuple[int, int, int] = (160, 230, 255)
    text_label: tuple[int, int, int] = (206, 222, 240)
    text_muted: tuple[int, int, int] = (118, 148, 178)
    text_btn_bright: tuple[int, int, int] = (255, 252, 248)
    text_btn_dim: tuple[int, int, int] = (210, 214, 222)
    rule_subtle: tuple[int, int, int] = (48, 64, 90)


DEFAULT_PIXEL_STYLE = PixelChromeStyle()


def line_width_for_scale(scale: int) -> int:
    return max(1, int(scale))


def inner_face_rect(outer: pygame.Rect, line_w: int) -> pygame.Rect:
    """Inner panel face rectangle after :func:`draw_panel_shell` triple rim."""
    groove = pygame.Rect(outer.x + line_w, outer.y + line_w, outer.w - 2 * line_w, outer.h - 2 * line_w)
    if groove.w < 4 or groove.h < 4:
        return outer
    return pygame.Rect(groove.x + line_w, groove.y + line_w, groove.w - 2 * line_w, groove.h - 2 * line_w)


def draw_panel_shell(
    surface: pygame.Surface,
    outer: pygame.Rect,
    line_w: int,
    style: PixelChromeStyle = DEFAULT_PIXEL_STYLE,
) -> None:
    pygame.draw.rect(surface, style.frame_rim, outer)
    groove = pygame.Rect(outer.x + line_w, outer.y + line_w, outer.w - 2 * line_w, outer.h - 2 * line_w)
    if groove.w < 4 or groove.h < 4:
        return
    pygame.draw.rect(surface, style.frame_groove, groove)
    face = inner_face_rect(outer, line_w)
    if face.w > 0 and face.h > 0:
        pygame.draw.rect(surface, style.panel_face, face)


def draw_horizontal_rule(
    surface: pygame.Surface,
    x0: int,
    x1: int,
    y: int,
    color: tuple[int, int, int],
    line_w: int,
) -> None:
    pygame.draw.line(surface, color, (x0, y), (x1, y), line_w)


def draw_well(surface: pygame.Surface, rect: pygame.Rect, line_w: int, style: PixelChromeStyle = DEFAULT_PIXEL_STYLE) -> None:
    pygame.draw.rect(surface, style.well_face, rect)
    pygame.draw.rect(surface, style.well_border, rect, line_w)


def draw_inset_control(surface: pygame.Surface, rect: pygame.Rect, line_w: int, style: PixelChromeStyle = DEFAULT_PIXEL_STYLE) -> None:
    pygame.draw.rect(surface, style.drop_face, rect)
    pygame.draw.rect(surface, style.drop_border, rect, line_w)


def draw_dropdown_arrow(surface: pygame.Surface, arrow: pygame.Rect, line_w: int, fg: tuple[int, int, int]) -> None:
    step = line_w
    cx = arrow.centerx
    y0 = arrow.centery - step
    for i, nw in enumerate((1, 3, 5)):
        w = nw * line_w
        x = cx - w // 2
        pygame.draw.rect(surface, fg, pygame.Rect(x, y0 + i * step, w, line_w))


def draw_primary_button(surface: pygame.Surface, rect: pygame.Rect, line_w: int, style: PixelChromeStyle = DEFAULT_PIXEL_STYLE) -> None:
    pygame.draw.rect(surface, style.btn_primary_face, rect)
    pygame.draw.rect(surface, style.btn_primary_border, rect, line_w)
    hi = pygame.Rect(rect.x + line_w, rect.y + line_w, rect.w - 2 * line_w, max(line_w, (rect.h - line_w * 2) // 3))
    if hi.w > 0 and hi.h > 0:
        tint = tuple(min(255, c + 26) for c in style.btn_primary_face)
        pygame.draw.rect(surface, tint, hi)


def draw_neutral_button(surface: pygame.Surface, rect: pygame.Rect, line_w: int, style: PixelChromeStyle = DEFAULT_PIXEL_STYLE) -> None:
    pygame.draw.rect(surface, style.btn_neutral_face, rect)
    pygame.draw.rect(surface, style.btn_neutral_border, rect, line_w)


def draw_toggle_track(
    surface: pygame.Surface,
    toggle_rect: pygame.Rect,
    enabled: bool,
    outline_w: int,
    knob_w: int,
    knob_mx: int,
    knob_my: int,
    style: PixelChromeStyle = DEFAULT_PIXEL_STYLE,
) -> None:
    """``knob_mx`` / ``knob_my`` are insets inside ``toggle_rect`` (multiply by window scale when needed)."""
    face, edge = (
        (style.togg_on_face, style.togg_on_border) if enabled else (style.togg_off_face, style.togg_off_border)
    )
    pygame.draw.rect(surface, face, toggle_rect)
    pygame.draw.rect(surface, edge, toggle_rect, width=outline_w)
    kh = max(outline_w, toggle_rect.h - 2 * knob_my)
    kx = toggle_rect.right - knob_w - knob_mx if enabled else toggle_rect.x + knob_mx
    pygame.draw.rect(surface, style.knob, pygame.Rect(kx, toggle_rect.y + knob_my, knob_w, kh))
