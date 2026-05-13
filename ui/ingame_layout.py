from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

import pygame

from app.fonts import load_ui_font


INTERNAL_RECTS = {
    "ranking_label": pygame.Rect(7, 6, 56, 16),
    "card_base": pygame.Rect(5, 28, 60, 20),
    "card_layout": pygame.Rect(5, 28, 60, 100),
    "head_base": pygame.Rect(7, 90, 16, 16),
    "head_eliminated": pygame.Rect(7, 110, 16, 16),
    "head_gold": pygame.Rect(7, 30, 16, 16),
    "head_silver": pygame.Rect(7, 50, 16, 16),
    "head_bronze": pygame.Rect(7, 70, 16, 16),
    "overlay_gold": pygame.Rect(5, 28, 60, 20),
    "overlay_silver": pygame.Rect(5, 48, 60, 20),
    "overlay_bronze": pygame.Rect(5, 68, 60, 20),
    "card_eliminated": pygame.Rect(5, 108, 60, 20),
    "rank_textbox": pygame.Rect(23, 30, 6, 10),
    "name_textbox": pygame.Rect(29, 30, 34, 10),
    "distance_textbox": pygame.Rect(23, 40, 40, 6),
    "game_time_textbox": pygame.Rect(21, 133, 41, 12),
    "game_time_icon": pygame.Rect(7, 133, 12, 12),
    "game_time_iconbox": pygame.Rect(7, 133, 12, 12),
    "eliminated_textbox": pygame.Rect(23, 90, 40, 16),
    "eliminated_icon": pygame.Rect(10, 93, 12, 12),
    "eliminated_iconbox": pygame.Rect(9, 92, 12, 12),
    "room_name_textbox": pygame.Rect(7, 149, 56, 12),
    "platforms_textbox": pygame.Rect(7, 161, 56, 12),
    "notification_finished_frame": pygame.Rect(135, 6, 120, 32),
    "notification_finished_icon": pygame.Rect(144, 15, 102, 14),
    "notification_finished_textbox": pygame.Rect(161, 15, 68, 14),
    "notification_eliminated_frame": pygame.Rect(135, 6, 120, 32),
    "notification_eliminated_icon": pygame.Rect(144, 15, 102, 14),
    "notification_eliminated_textbox": pygame.Rect(161, 15, 68, 14),
    "effects_icon_layout": pygame.Rect(78, 144, 235, 34),
    "effects_iconbox": pygame.Rect(77, 162, 16, 16),
    "effects_iconbox_layout": pygame.Rect(77, 144, 236, 34),
    "effects_textbox": pygame.Rect(95, 162, 31, 16),
    "effects_textbox_layout": pygame.Rect(95, 144, 200, 34),
}

ASSET_FILES = {
    "card_base": "06_InGamePanelRankingCardBase_Frame.png",
    "head_base": "04_InGamePanelRankingCardHeadTextureBase_Frame.png",
    "head_eliminated": "05_InGamePanelRankingCardHeadTextureBaseEliminated_Frame.png",
    "head_gold": "08_InGamePanelRankingCardHeadTextureGold_Frame.png",
    "head_silver": "09_InGamePanelRankingCardHeadTextureSilver_Frame.png",
    "head_bronze": "10_InGamePanelRankingCardHeadTextureBronze_Frame.png",
    "overlay_gold": "12_InGamePanelRankingCardOverlayGold_Frame.png",
    "overlay_silver": "13_InGamePanelRankingCardOverlaySilver_Frame.png",
    "overlay_bronze": "11_InGamePanelRankingCardOverlayBronze_Frame.png",
    "card_eliminated": "14_InGamePanelRankingCardBaseEliminated_Frame.png",
    "game_time_icon": "19_InGamePaneGameTime_Icon.png",
    "eliminated_icon": "22_InGamePanelRankingCardOverlayBaseEliminated_Icon.png",
    "notification_finished_frame": "26_InGameNotificationFinished_Frame.png",
    "notification_finished_icon": "27_InGameNotificationFinished_Icon.png",
    "notification_eliminated_frame": "29_InGameNotificationEliminated_Frame.png",
    "notification_eliminated_icon": "30_InGameNotificationEliminated_Icon.png",
}

EFFECT_ICON_FILES = {
    "Speed Buff": "01_SpeedBoost.png",
    "Jump Buff": "02_JumpBoost.png",
    "Shield Aura": "03_ShieldBuff.png",
    "Double Jump": "04_DoubleJumpBuff.png",
    "Launch Boost": "05_LaunchBoost.png",
    "Reverse Control": "06_ReverseControlDebuff.png",
    "Slippery": "07_SlipperyDebuff.png",
    "Slow Falling": "08_SlowFallingBuff.png",
    "Heavy": "09_HeavyDebuff.png",
    "Weak Jump": "10_WeakJumpDebuff.png",
}


BUFF_LABELS = ("Speed Buff", "Jump Buff", "Shield Aura", "Double Jump", "Launch Boost", "Slow Falling")
DEBUFF_LABELS = ("Reverse Control", "Slippery", "Heavy", "Weak Jump")


@dataclass(frozen=True)
class RankingRow:
    player_id: int | None
    rank: int
    name: str
    status: Literal["live", "finished", "eliminated", "open"]
    platforms_reached: int
    distance_text: str
    avatar: pygame.Surface | None = None


@dataclass(frozen=True)
class InGameNotification:
    kind: Literal["finished", "eliminated"]
    name: str
    placement: int


class InGameLayoutRenderer:
    def __init__(self, project_root: Path):
        self._project_root = project_root
        root = project_root / "assets" / "inGame"
        self.assets = {
            key: pygame.image.load(str(root / filename)).convert_alpha()
            for key, filename in ASSET_FILES.items()
        }
        icon_root = root / "BuffDebuffIcons"
        self.effect_icons = {
            label: pygame.image.load(str(icon_root / filename)).convert_alpha()
            for label, filename in EFFECT_ICON_FILES.items()
            if (icon_root / filename).exists()
        }
        self._font_cache: dict[tuple[int, bool], pygame.font.Font] = {}

    def draw(
        self,
        surface: pygame.Surface,
        scale: int,
        rows: list[RankingRow],
        match_elapsed_sec: float | None,
        room_name: str,
        platforms_reached: int,
        effect_timers: Mapping[str, float],
        notification: InGameNotification | None,
        elapsed: float,
    ) -> None:
        self._draw_ranking(surface, scale, rows, elapsed)
        self._draw_match_info(surface, scale, match_elapsed_sec, room_name, platforms_reached)
        self._draw_effects(surface, scale, effect_timers)
        if notification is not None:
            self._draw_notification(surface, scale, notification)

    def _font(self, px: int, bold: bool = True) -> pygame.font.Font:
        key = (max(6, int(px)), bold)
        font = self._font_cache.get(key)
        if font is None:
            font = load_ui_font(self._project_root, key[0], bold=bold)
            self._font_cache[key] = font
        return font

    def _window_rect(self, rect: pygame.Rect, scale: int) -> pygame.Rect:
        return pygame.Rect(rect.x * scale, rect.y * scale, rect.w * scale, rect.h * scale)

    def _offset_rect(self, template: pygame.Rect, row_y: int) -> pygame.Rect:
        return pygame.Rect(template.x, row_y + (template.y - 28), template.w, template.h)

    def _draw_asset(self, surface: pygame.Surface, key: str, rect: pygame.Rect, scale: int) -> None:
        target = self._window_rect(rect, scale)
        image = self.assets[key]
        if image.get_size() == target.size:
            surface.blit(image, target)
            return
        surface.blit(pygame.transform.scale(image, target.size), target)

    def _draw_image(self, surface: pygame.Surface, image: pygame.Surface, rect: pygame.Rect, scale: int) -> None:
        target = self._window_rect(rect, scale)
        surface.blit(pygame.transform.scale(image, target.size), target)

    def _fit_font(self, text: str, rect: pygame.Rect, scale: int, max_internal_px: int, bold: bool = True) -> pygame.font.Font:
        max_px = max(6, max_internal_px * scale)
        min_px = max(5, 4 * scale)
        for size in range(max_px, min_px - 1, -1):
            font = self._font(size, bold=bold)
            tw, th = font.size(text)
            if tw <= rect.w * scale and th <= rect.h * scale + scale:
                return font
        return self._font(min_px, bold=bold)

    def _draw_text_center(
        self,
        surface: pygame.Surface,
        text: str,
        rect: pygame.Rect,
        scale: int,
        color: tuple[int, int, int] = (244, 248, 255),
        max_internal_px: int = 7,
        bold: bool = True,
    ) -> None:
        if not text:
            return
        target = self._window_rect(rect, scale)
        font = self._fit_font(text, rect, scale, max_internal_px, bold=bold)
        label = font.render(text, True, color)
        surface.blit(label, label.get_rect(center=target.center))

    def _draw_text_left(
        self,
        surface: pygame.Surface,
        text: str,
        rect: pygame.Rect,
        scale: int,
        color: tuple[int, int, int] = (244, 248, 255),
        max_internal_px: int = 7,
        bold: bool = True,
    ) -> None:
        if not text:
            return
        target = self._window_rect(rect, scale)
        font = self._fit_font(text, rect, scale, max_internal_px, bold=bold)
        label = font.render(text, True, color)
        surface.blit(label, label.get_rect(midleft=(target.x, target.centery)))

    def _draw_text_right(
        self,
        surface: pygame.Surface,
        text: str,
        rect: pygame.Rect,
        scale: int,
        color: tuple[int, int, int] = (244, 248, 255),
        max_internal_px: int = 7,
        bold: bool = True,
    ) -> None:
        if not text:
            return
        target = self._window_rect(rect, scale)
        font = self._fit_font(text, rect, scale, max_internal_px, bold=bold)
        label = font.render(text, True, color)
        surface.blit(label, label.get_rect(midright=(target.right, target.centery)))

    def _draw_marquee_text(
        self,
        surface: pygame.Surface,
        text: str,
        rect: pygame.Rect,
        scale: int,
        elapsed: float,
        color: tuple[int, int, int] = (244, 248, 255),
    ) -> None:
        target = self._window_rect(rect, scale)
        font = self._font(5 * scale, bold=True)
        label = font.render(text, True, color)
        if label.get_width() <= target.w:
            surface.blit(label, label.get_rect(midleft=(target.x + scale, target.centery)))
            return

        clip = pygame.Surface(target.size, pygame.SRCALPHA)
        max_scroll = label.get_width() - target.w + 2 * scale
        period = max(2.4, max_scroll / max(18.0 * scale, 1.0))
        cycle = (elapsed % (period * 2.0)) / period
        if cycle <= 1.0:
            scroll = cycle * max_scroll
        else:
            scroll = (2.0 - cycle) * max_scroll
        clip.blit(label, (scale - int(scroll), (target.h - label.get_height()) // 2))
        surface.blit(clip, target)

    def _draw_dark_overlay(self, surface: pygame.Surface, rect: pygame.Rect, scale: int) -> None:
        target = self._window_rect(rect, scale)
        overlay = pygame.Surface(target.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        surface.blit(overlay, target)

    def _draw_ranking(self, surface: pygame.Surface, scale: int, rows: list[RankingRow], elapsed: float) -> None:
        # 56×16 label; y=6 centers it in the 28px strip above the first ranking row (y=28).
        self._draw_text_center(surface, "RANKINGS", INTERNAL_RECTS["ranking_label"], scale, max_internal_px=12)

        overlay_keys = ("overlay_gold", "overlay_silver", "overlay_bronze")
        head_keys = ("head_gold", "head_silver", "head_bronze")
        for index in range(5):
            row_y = 28 + index * 20
            row = rows[index] if index < len(rows) else RankingRow(None, index + 1, "Open Slot", "open", 0, "")
            row_rect = pygame.Rect(5, row_y, 60, 20)
            base_key = "card_eliminated" if row.status == "eliminated" and index >= 3 else "card_base"
            self._draw_asset(surface, base_key, row_rect, scale)

            if index < 3:
                head_key = head_keys[index]
            else:
                head_key = "head_eliminated" if row.status == "eliminated" else "head_base"
            head_rect = pygame.Rect(7, row_y + 2, 16, 16)

            if row.avatar is not None and row.status != "open":
                self._draw_image(surface, row.avatar, head_rect, scale)
            if row.status == "eliminated":
                self._draw_dark_overlay(surface, head_rect, scale)
            self._draw_asset(surface, head_key, head_rect, scale)

            if index < 3:
                self._draw_asset(surface, overlay_keys[index], row_rect, scale)
                if row.status == "eliminated":
                    self._draw_dark_overlay(surface, row_rect, scale)

            if row.status == "eliminated":
                self._draw_eliminated_badge(surface, row_y, scale)
                continue

            name_rect = self._offset_rect(INTERNAL_RECTS["name_textbox"], row_y)
            if row.status == "open":
                self._draw_text_center(surface, "Open Slot", name_rect, scale, (206, 214, 224), max_internal_px=5)
                continue

            rank_rect = self._offset_rect(INTERNAL_RECTS["rank_textbox"], row_y)
            dist_rect = self._offset_rect(INTERNAL_RECTS["distance_textbox"], row_y)
            self._draw_text_center(surface, str(row.rank), rank_rect, scale, max_internal_px=5)
            self._draw_marquee_text(surface, row.name, name_rect, scale, elapsed)
            self._draw_text_center(
                surface, row.distance_text, dist_rect, scale, (188, 198, 210), max_internal_px=5, bold=False
            )

    def _draw_eliminated_badge(self, surface: pygame.Surface, row_y: int, scale: int) -> None:
        textbox = pygame.Rect(23, row_y + 2, 40, 16)
        icon = pygame.Rect(9, row_y + 4, 12, 12)
        self._draw_asset(surface, "eliminated_icon", icon, scale)
        self._draw_text_center(surface, "ELIMINATED", textbox, scale, (238, 74, 82), max_internal_px=6)

    def _draw_match_info(
        self,
        surface: pygame.Surface,
        scale: int,
        match_elapsed_sec: float | None,
        room_name: str,
        platforms_reached: int,
    ) -> None:
        self._draw_asset(surface, "game_time_icon", INTERNAL_RECTS["game_time_icon"], scale)
        self._draw_text_center(surface, self._format_clock(match_elapsed_sec), INTERNAL_RECTS["game_time_textbox"], scale, max_internal_px=6)

        self._draw_text_center(surface, room_name or "Room", INTERNAL_RECTS["room_name_textbox"], scale, max_internal_px=6)

        self._draw_text_center(
            surface,
            f"Platform: {platforms_reached}",
            INTERNAL_RECTS["platforms_textbox"],
            scale,
            max_internal_px=5,
            bold=False,
        )

    def _format_clock(self, seconds: float | None) -> str:
        if seconds is None:
            return "0.0s"
        seconds = max(0.0, float(seconds))
        mins = int(seconds // 60)
        secs = seconds % 60.0
        if mins > 0:
            return f"{mins}:{secs:04.1f}"
        return f"{secs:.1f}s"

    def _draw_notification(self, surface: pygame.Surface, scale: int, notification: InGameNotification) -> None:
        prefix = "notification_finished" if notification.kind == "finished" else "notification_eliminated"
        self._draw_asset(surface, f"{prefix}_frame", INTERNAL_RECTS[f"{prefix}_frame"], scale)
        self._draw_asset(surface, f"{prefix}_icon", INTERNAL_RECTS[f"{prefix}_icon"], scale)
        textbox = INTERNAL_RECTS[f"{prefix}_textbox"]
        verb = "FINISHED" if notification.kind == "finished" else "ELIMINATED"
        self._draw_text_center(surface, f"{notification.name} {verb}", textbox, scale, max_internal_px=5)

    def _draw_effects(self, surface: pygame.Surface, scale: int, effect_timers: Mapping[str, float]) -> None:
        buffs = [(label, effect_timers[label]) for label in BUFF_LABELS if effect_timers.get(label, 0.0) > 0.0][:3]
        debuffs = [(label, effect_timers[label]) for label in DEBUFF_LABELS if effect_timers.get(label, 0.0) > 0.0][:3]

        buff_slots = [
            (pygame.Rect(77, 162, 16, 16), pygame.Rect(97, 162, 31, 16)),
            (pygame.Rect(128, 162, 16, 16), pygame.Rect(148, 162, 31, 16)),
            (pygame.Rect(77, 144, 16, 16), pygame.Rect(97, 144, 31, 16)),
        ]
        debuff_slots = [
            (pygame.Rect(297, 162, 16, 16), pygame.Rect(264, 162, 31, 16)),
            (pygame.Rect(247, 162, 16, 16), pygame.Rect(214, 162, 31, 16)),
            (pygame.Rect(297, 144, 16, 16), pygame.Rect(264, 144, 31, 16)),
        ]
        for label, remaining, slot in [(label, remaining, buff_slots[i]) for i, (label, remaining) in enumerate(buffs)]:
            self._draw_effect_slot(surface, scale, label, remaining, slot[0], slot[1], "left")
        for label, remaining, slot in [(label, remaining, debuff_slots[i]) for i, (label, remaining) in enumerate(debuffs)]:
            self._draw_effect_slot(surface, scale, label, remaining, slot[0], slot[1], "right")

    def _draw_effect_slot(
        self,
        surface: pygame.Surface,
        scale: int,
        label: str,
        remaining: float,
        icon_rect: pygame.Rect,
        text_rect: pygame.Rect,
        text_align: Literal["left", "right"],
    ) -> None:
        icon = self.effect_icons.get(label)
        if icon is not None:
            self._draw_image(surface, icon, icon_rect, scale)
        if text_align == "right":
            self._draw_text_right(surface, f"{remaining:.1f}s", text_rect, scale, max_internal_px=5, bold=False)
        else:
            self._draw_text_left(surface, f"{remaining:.1f}s", text_rect, scale, max_internal_px=5, bold=False)
