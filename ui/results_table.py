"""Match-results dungeon-style standings board (drawn over a tiled backdrop)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import pygame

from app.fonts import load_ui_font
from app.paths import get_resource_root
from ui import animations as anim
from ui.pixel_chrome import DEFAULT_PIXEL_STYLE, draw_panel_shell
from ui.theme import DEFAULT_THEME, Theme
from ui.widgets import truncate_text_to_px
from world.assets import WorldAssets
from world.constants import INTERNAL_HEIGHT, INTERNAL_WIDTH
from world.rendering import draw_static_game_frame


_BRICK_BASE = (38, 44, 58)
_TORCH_WOOD = (85, 55, 35)
_PANEL_FILL = (22, 28, 46)
_GOLD = (230, 190, 72)
_GOLD_DIM = (180, 145, 55)
_BRONZE = (168, 110, 62)
_SILVER = (150, 160, 176)


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


def _winner_badge_top_font(detail_f: pygame.font.Font) -> pygame.font.Font:
    sz = max(8, min(11, detail_f.get_height() - 4))
    return load_ui_font(get_resource_root(), sz, bold=False)


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
    pygame.draw.rect(s, (55, 62, 78), s.get_rect())
    pygame.draw.circle(s, (120, 130, 148), (size // 2, size // 2 - 2), size // 5)
    pygame.draw.rect(s, (120, 130, 148), pygame.Rect(size // 2 - size // 5, size // 2 + 2, size * 2 // 5, size // 4))
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
    default_avatar: Optional[pygame.Surface] = None,
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

    scrim = pygame.Surface((w, h), pygame.SRCALPHA)
    scrim.fill((0, 0, 0, 128))
    surface.blit(scrim, (0, 0))

    px_style = DEFAULT_PIXEL_STYLE
    rim_w = max(2, min(4, h // 180))

    title_s = title_f.render("MATCH RESULTS", True, px_style.text_title)
    title_h = title_s.get_height()
    title_pad_x = max(20, h // 18)
    title_pad_y = max(6, h // 60)
    banner_h = title_h + title_pad_y * 2
    banner_w = title_s.get_width() + title_pad_x * 2
    title_gap = max(8, min(14, h // 14))
    footer_reserve = 28 + max(0, footer_reserve_extra)

    pw = min(760, w - 16)
    nrows = len(rows)
    max_panel_h = max(60, h - footer_reserve - banner_h - title_gap - 10)
    top_bottom = 12
    header_h = min(34, max(24, max_panel_h // (max(4, nrows + 2))))
    inner_pad_bottom = 16
    row_h = max(34, min(56, (max_panel_h - top_bottom - header_h - inner_pad_bottom) // max(1, nrows)))
    panel_h = top_bottom + header_h + nrows * row_h + inner_pad_bottom
    if panel_h > max_panel_h:
        row_h = max(30, (max_panel_h - top_bottom - header_h - inner_pad_bottom) // max(1, nrows))
        panel_h = top_bottom + header_h + nrows * row_h + inner_pad_bottom

    block_h = banner_h + title_gap + panel_h
    top = max(6, (h - block_h - footer_reserve) // 2)
    banner = pygame.Rect(0, 0, banner_w, banner_h)
    banner.midtop = (w // 2, top)
    draw_panel_shell(surface, banner, rim_w, px_style)
    surface.blit(title_s, title_s.get_rect(center=banner.center))
    panel = pygame.Rect((w - pw) // 2, top + banner_h + title_gap, pw, panel_h)
    draw_panel_shell(surface, panel, rim_w, px_style)

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

    hdr_y = iy + 6
    h_name = detail_f.render("NAME", True, theme.text_muted)
    h_time = detail_f.render(time_label, True, theme.text_muted)
    h_plat = detail_f.render(plat_label, True, theme.text_muted)
    header_bar = pygame.Rect(inner.x, iy, inner.w, max(24, header_h - 4))
    pygame.draw.rect(surface, px_style.well_face, header_bar)
    surface.blit(h_name, (x_name, hdr_y))
    surface.blit(h_time, (right_time - h_time.get_width(), hdr_y))
    surface.blit(h_plat, (right_plat - h_plat.get_width(), hdr_y))
    hdr_rule_y = hdr_y + max(24, header_h - 10)
    pygame.draw.line(surface, px_style.frame_rim, (inner.x, hdr_rule_y), (inner.right, hdr_rule_y), 1)

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

        if i % 2 == 1 and not is_winner:
            stripe = pygame.Surface(row_rect.size, pygame.SRCALPHA)
            stripe.fill((*px_style.well_face, 90))
            surface.blit(stripe, row_rect.topleft)

        if is_winner:
            glow = pygame.Surface(row_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*_GOLD, int(70 * alpha)), glow.get_rect())
            surface.blit(glow, row_rect.topleft)
            pygame.draw.rect(surface, _GOLD, row_rect, width=2)

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

        pygame.draw.rect(surface, bcol, badge_rect)
        pygame.draw.rect(surface, bborder, badge_rect, width=2)
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
        if avatar_source is None and default_avatar is not None:
            avatar_source = default_avatar
        if avatar_source is not None:
            scaled = pygame.transform.smoothscale(avatar_source, (av_size, av_size))
            surface.blit(scaled, (av_x, av_y))
            pygame.draw.rect(surface, px_style.frame_rim, pygame.Rect(av_x, av_y, av_size, av_size), width=1)
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
