from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class PerformanceOverlayData:
    fps: float | None
    ping_ms: float | None
    ping_avg_ms: float | None = None
    ping_min_ms: float | None = None
    ping_max_ms: float | None = None
    ping_jitter_ms: float | None = None
    ping_p95_ms: float | None = None
    ping_session_avg_ms: float | None = None
    ping_session_min_ms: float | None = None
    ping_session_max_ms: float | None = None
    heartbeat_loss_pct: float = 0.0
    inbound_kib_per_sec: float = 0.0
    inbound_avg_kib_per_sec: float = 0.0
    inbound_min_kib_per_sec: float = 0.0
    inbound_max_kib_per_sec: float = 0.0
    outbound_kib_per_sec: float = 0.0
    outbound_avg_kib_per_sec: float = 0.0
    outbound_min_kib_per_sec: float = 0.0
    outbound_max_kib_per_sec: float = 0.0


def _format_value(value: float | None, suffix: str, digits: int = 0) -> str:
    if value is None:
        return f"--{suffix}"
    if digits <= 0:
        return f"{int(round(value))}{suffix}"
    return f"{value:.{digits}f}{suffix}"


# Widest strings we expect per layout tier (stable box width; avoids jitter when values update).
_REF_WIDTH_DETAILED = (
    "FPS 999  RTT 9999ms  μ999 999/999  σ999 p95 9999  L100.0%  "
    "Sμ999[999…999]  "
    "↓9999.9/9999.9/9999.9/9999.9  "
    "↑9999.9/9999.9/9999.9/9999.9 KiB/s"
)
_REF_WIDTH_MEDIUM = (
    "FPS 999  RTT 9999ms  μ999 σ999 p95 9999  L100.0%  "
    "↓9999.9/9999.9 ↑9999.9/9999.9 KiB/s"
)
_REF_WIDTH_TIGHT = "FPS 999 RTT 9999ms μ999 σ999 L100.0% ↓9999.9↑9999.9"


def _build_perf_lines(
    metrics: PerformanceOverlayData,
) -> tuple[str, str, str]:
    fps = _format_value(metrics.fps, "", digits=0)
    rtt = _format_value(metrics.ping_ms, "ms", digits=0)
    wavg = _format_value(metrics.ping_avg_ms, "", digits=0)
    wmin = _format_value(metrics.ping_min_ms, "", digits=0)
    wmax = _format_value(metrics.ping_max_ms, "", digits=0)
    jit = _format_value(metrics.ping_jitter_ms, "", digits=0)
    p95 = _format_value(metrics.ping_p95_ms, "", digits=0)
    sess_avg = _format_value(metrics.ping_session_avg_ms, "", digits=0)
    sess_lo = _format_value(metrics.ping_session_min_ms, "", digits=0)
    sess_hi = _format_value(metrics.ping_session_max_ms, "", digits=0)
    loss = metrics.heartbeat_loss_pct
    loss_s = f"{loss:.1f}%" if metrics.ping_ms is not None or metrics.heartbeat_loss_pct > 0 else "--%"
    net_in = max(0.0, float(metrics.inbound_kib_per_sec))
    net_in_avg = max(0.0, float(metrics.inbound_avg_kib_per_sec))
    net_in_min = max(0.0, float(metrics.inbound_min_kib_per_sec))
    net_in_max = max(0.0, float(metrics.inbound_max_kib_per_sec))
    net_out = max(0.0, float(metrics.outbound_kib_per_sec))
    net_out_avg = max(0.0, float(metrics.outbound_avg_kib_per_sec))
    net_out_min = max(0.0, float(metrics.outbound_min_kib_per_sec))
    net_out_max = max(0.0, float(metrics.outbound_max_kib_per_sec))

    detailed = (
        f"FPS {fps}  RTT {rtt}  μ{wavg} {wmin}/{wmax}  σ{jit} p95 {p95}  L{loss_s}  "
        f"Sμ{sess_avg}[{sess_lo}…{sess_hi}]  "
        f"↓{net_in:.1f}/{net_in_avg:.1f}/{net_in_min:.1f}/{net_in_max:.1f}  "
        f"↑{net_out:.1f}/{net_out_avg:.1f}/{net_out_min:.1f}/{net_out_max:.1f} KiB/s"
    )
    medium = (
        f"FPS {fps}  RTT {rtt}  μ{wavg} σ{jit} p95 {p95}  L{loss_s}  "
        f"↓{net_in:.1f}/{net_in_avg:.1f} ↑{net_out:.1f}/{net_out_avg:.1f} KiB/s"
    )
    tight = f"FPS {fps} RTT {rtt} μ{wavg} σ{jit} L{loss_s} ↓{net_in:.1f}↑{net_out:.1f}"
    return detailed, medium, tight


# Must stay in sync with vertical placement inside draw_performance_overlay (panel_y + panel_h).
_PERF_OVERLAY_TOP_MARGIN = 4
_PERF_OVERLAY_PAD_Y = 3


def playable_area_top_after_performance_bar(font: pygame.font.Font, overlay_enabled: bool, anchor_y: int = 0) -> int:
    """
    Y coordinate (window pixels) where stacked gameplay HUD can start without touching the perf bar.
    When the overlay is disabled, returns a small top inset below anchor_y.
    """
    if not overlay_enabled:
        return anchor_y + 6
    probe = font.render("|", True, (255, 255, 255))
    line_h = probe.get_height()
    panel_h = line_h + _PERF_OVERLAY_PAD_Y * 2
    gap_below_bar = 4
    return anchor_y + _PERF_OVERLAY_TOP_MARGIN + panel_h + gap_below_bar


def draw_performance_overlay(
    surface: pygame.Surface,
    font: pygame.font.Font,
    metrics: PerformanceOverlayData,
    anchor_rect: pygame.Rect | None = None,
) -> None:
    rect = anchor_rect or surface.get_rect()
    if rect.w <= 12 or rect.h <= 12:
        return

    pad_x = 6
    pad_y = _PERF_OVERLAY_PAD_Y
    detailed, medium, tight = _build_perf_lines(metrics)
    max_text_w = max(8, rect.w - 8 - pad_x * 2)

    line = detailed
    ref_width_line = _REF_WIDTH_DETAILED
    if font.size(line)[0] > max_text_w:
        line = medium
        ref_width_line = _REF_WIDTH_MEDIUM
    if font.size(line)[0] > max_text_w:
        line = tight
        ref_width_line = _REF_WIDTH_TIGHT

    label = font.render(line, True, (232, 240, 248))
    stable_inner_w = max(font.size(ref_width_line)[0], label.get_width())
    margin_x = 4
    max_panel_w = max(8, rect.w - 2 * margin_x)
    panel_w = min(max_panel_w, stable_inner_w + pad_x * 2)
    line_h = label.get_height()
    panel_h = line_h + pad_y * 2
    panel_x = rect.x + (rect.w - panel_w) // 2
    panel_y = rect.y + _PERF_OVERLAY_TOP_MARGIN
    panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
    bg = pygame.Surface(panel.size, pygame.SRCALPHA)
    bg.fill((3, 10, 20, 188))
    surface.blit(bg, panel.topleft)
    pygame.draw.rect(surface, (80, 122, 156), panel, width=1, border_radius=4)
    text_x = panel.x + (panel.w - label.get_width()) // 2
    text_y = panel.y + (panel.h - label.get_height()) // 2
    surface.blit(label, (text_x, text_y))
