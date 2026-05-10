"""Match-results dungeon-style standings board (drawn over a tiled backdrop)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import pygame

from ui import animations as anim
from ui.theme import DEFAULT_THEME, Theme
from ui.widgets import truncate_text_to_px
from world.assets import WorldAssets
from world.constants import INTERNAL_HEIGHT, INTERNAL_WIDTH
from world.rendering import draw_static_game_frame


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
    Standings rows: ``(player_id, placement, name)`` or extended ``(…, elapsed_centisec, platforms)``.
    fonts: ``(title_font, name_column_font, detail_font)``

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

    inner = panel.inflate(-12, -26)
    iy = inner.y + 6
    pad_inner = 8
    content_left = inner.x + pad_inner
    content_right = inner.right - pad_inner
    usable_w = content_right - content_left

    # Pick header labels and column widths from rendered text. Designed for the
    # 2x = 640x360 minimum window; wider windows just get more name room.
    col_gap = 12
    av_size = min(42, max(28, (row_h - 8)))
    col_av = av_size
    gap_after_av = 8
    badge_h = max(24, row_h - 14)
    col_badge = max(
        detail_f.size("WINNER")[0] + 10,  # widest stacked label
        detail_f.size("99TH")[0] + 12,
    )

    sample_time = detail_f.size("00m 00s")[0]
    sample_plat = detail_f.size("99")[0]

    def _fit_columns(plat_label: str, time_label: str):
        plat_w = max(detail_f.size(plat_label)[0], sample_plat) + 4
        time_w = max(detail_f.size(time_label)[0], sample_time) + 4
        fixed = col_badge + col_av + gap_after_av + col_gap + time_w + col_gap + plat_w
        name_room = usable_w - fixed
        return plat_w, time_w, name_room

    plat_label, time_label = "PLATFORMS", "TIME PLAYED"
    col_plat_w, col_time_w, name_max_w = _fit_columns(plat_label, time_label)
    if name_max_w < 60:
        plat_label, time_label = "PLAT", "TIME"
        col_plat_w, col_time_w, name_max_w = _fit_columns(plat_label, time_label)
    name_max_w = max(28, name_max_w)

    right_plat = content_right
    left_plat = right_plat - col_plat_w
    right_time = left_plat - col_gap
    left_time = right_time - col_time_w
    badge_left = content_left
    badge_right = badge_left + col_badge
    x_av = badge_right + 4
    x_name = x_av + col_av + gap_after_av

    sep_col = detail_f.render("◆", True, (80, 120, 180))
    hdr_y = iy + 6
    h_name = detail_f.render("NAME", True, theme.text_muted)
    h_time = detail_f.render(time_label, True, theme.text_muted)
    h_plat = detail_f.render(plat_label, True, theme.text_muted)
    surface.blit(h_name, (x_name, hdr_y))
    sep_half = sep_col.get_width() // 2
    sep1x = (x_name + name_max_w + left_time) // 2 - sep_half
    surface.blit(sep_col, (sep1x, hdr_y))
    surface.blit(h_time, (right_time - h_time.get_width(), hdr_y))
    sep2x = (right_time + left_plat) // 2 - sep_half
    surface.blit(sep_col, (sep2x, hdr_y))
    surface.blit(h_plat, (right_plat - h_plat.get_width(), hdr_y))
    hdr_rule_y = hdr_y + max(24, header_h - 10)
    pygame.draw.line(surface, _PANEL_INNER, (inner.x, hdr_rule_y), (inner.right, hdr_rule_y), 1)

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

        badge_rect = pygame.Rect(badge_left, y + (row_h - badge_h) // 2, col_badge - 4, badge_h)
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
        else:
            bt = detail_f.render(badge_txt, True, theme.text)
            surface.blit(bt, bt.get_rect(center=badge_rect.center))

        av_x = x_av
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

        nm = truncate_text_to_px((name or "")[:48], name_f, name_max_w)
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
