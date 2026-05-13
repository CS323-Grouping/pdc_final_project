"""Low-level UI primitives: buttons, text inputs, confirm dialogs, lock icon, text utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Tuple

import pygame

from ui.theme import DEFAULT_THEME, Theme


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
    body, _hint = fonts
    cap = body.render(inp.label, True, theme.text_muted)
    surface.blit(cap, (inp.rect.x, inp.rect.y - 22))
    pygame.draw.rect(surface, theme.bg_input, inp.rect, border_radius=6)
    bc = theme.border_focus if inp.focused else theme.border
    pygame.draw.rect(surface, bc, inp.rect, width=2, border_radius=6)
    surface.blit(
        body.render(inp.value, True, theme.text),
        (inp.rect.x + 10, inp.rect.y + (inp.rect.height - body.get_height()) // 2),
    )


def draw_lock_icon(surface: pygame.Surface, rect: pygame.Rect, color: Tuple[int, int, int]) -> None:
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    sh = max(3, h // 4)
    body = pygame.Rect(x + w // 4, y + sh, w // 2, h - sh)
    arch_w = w // 2 + 4
    arch = pygame.Rect(x + (w - arch_w) // 2, y, arch_w, sh + 4)
    pygame.draw.rect(surface, color, body, border_radius=3)
    pygame.draw.arc(surface, color, arch, 3.14159, 6.28318, 3)


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


def truncate_text_to_px(text: str, font: pygame.font.Font, max_width: int) -> str:
    """Truncate ``text`` with an ellipsis so its rendered width fits ``max_width``."""
    if max_width <= 12 or font.size(text)[0] <= max_width:
        return text
    ell = "…"
    t = text
    while len(t) > 1 and font.size(t + ell)[0] > max_width:
        t = t[:-1]
    return t + ell if t != text else text
