from pathlib import Path

import pygame

from player_scripts.animation import load_spritesheet_frames
from player_scripts.avatar_sprite import (
    AVATAR_RECT,
    VALID_AVATAR_EXTENSIONS,
    crop_square,
    make_default_avatar,
    prepare_avatar,
)
from states.common import ScreenState
from ui import components as ui
from ui.theme import DEFAULT_THEME
from world.constants import PLAYER_FRAME_HEIGHT, PLAYER_FRAME_WIDTH


class AvatarSetupState(ScreenState):
    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.back_button = ui.Button(pygame.Rect(0, 0, 110, 38), "Back")
        self.upload_button = ui.Button(pygame.Rect(0, 0, 160, 40), "Upload Image")
        self.default_button = ui.Button(pygame.Rect(0, 0, 150, 40), "Use Default")
        self.save_crop_button = ui.Button(pygame.Rect(0, 0, 130, 38), "Save Crop")
        self.cancel_crop_button = ui.Button(pygame.Rect(0, 0, 110, 38), "Cancel")
        self.zoom_in_button = ui.Button(pygame.Rect(0, 0, 42, 38), "+")
        self.zoom_out_button = ui.Button(pygame.Rect(0, 0, 42, 38), "-")
        self._back_h = False
        self._upload_h = False
        self._default_h = False
        self._save_h = False
        self._cancel_h = False
        self._zoom_in_h = False
        self._zoom_out_h = False
        self._body_frames = None
        self._idle_body_frame: pygame.Surface | None = None
        self._crop_preview: pygame.Surface | None = None
        self._editing_source: pygame.Surface | None = None
        self._editing_source_name = ""
        self._crop_zoom = 1.0
        self._crop_offset = pygame.Vector2(0, 0)
        self._crop_rect = pygame.Rect(0, 0, 220, 220)
        self._dragging_crop = False
        self._last_drag_pos = pygame.Vector2(0, 0)

    def enter(self):
        self._load_body_frames()
        self._refresh_previews()

    def _sprite_path(self) -> Path:
        return (
            self.context.project_root
            / "assets"
            / "player"
            / "animation"
            / "playerAnimationNormal_Blue.png"
        )

    def _load_body_frames(self):
        try:
            self._body_frames = load_spritesheet_frames(self._sprite_path())
        except (FileNotFoundError, pygame.error) as err:
            self._body_frames = None
            self.context.set_status(f"Could not load player preview: {err}", duration=4.0)

    def _current_avatar(self) -> pygame.Surface:
        return self.context.avatar_surface if self.context.avatar_surface is not None else make_default_avatar()

    def _current_crop_source(self) -> pygame.Surface:
        if self.context.avatar_window_surface is not None:
            return self.context.avatar_window_surface
        return self._current_avatar()

    def _refresh_previews(self):
        if self._body_frames is not None:
            self._idle_body_frame = self._body_frames["idle_front"][0]
        self._crop_preview = self._make_crop_preview(self._current_crop_source())

    def _make_crop_preview(self, source: pygame.Surface) -> pygame.Surface:
        return pygame.transform.smoothscale(crop_square(source), (112, 112))

    def _layout(self):
        width, height = self.context.screen.get_size()
        self.back_button.rect.topleft = (16, 16)
        button_y = height - 58
        self.upload_button.rect.center = (width // 2 - 90, button_y + 20)
        self.default_button.rect.center = (width // 2 + 90, button_y + 20)

    def _crop_layout(self):
        width, height = self.context.screen.get_size()
        size = min(240, width - 180, height - 116)
        size = max(140, size)
        self._crop_rect = pygame.Rect(0, 0, size, size)
        self._crop_rect.center = (width // 2, height // 2 - 8)
        self.zoom_in_button.rect.topleft = (self._crop_rect.right + 18, self._crop_rect.y + 12)
        self.zoom_out_button.rect.topleft = (self._crop_rect.right + 18, self.zoom_in_button.rect.bottom + 10)
        self.save_crop_button.rect.center = (width // 2 - 76, height - 38)
        self.cancel_crop_button.rect.center = (width // 2 + 74, height - 38)

    def _browse_avatar_file(self) -> Path | None:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            self.context.set_status("File browser is not available in this Python install.", duration=4.0)
            return None

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        selected = filedialog.askopenfilename(
            title="Choose avatar image",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("JPG", "*.jpg *.jpeg"),
            ),
        )
        root.destroy()
        if not selected:
            return None
        return Path(selected)

    def _upload_avatar(self):
        path = self._browse_avatar_file()
        if path is None:
            return
        if path.suffix.lower() not in VALID_AVATAR_EXTENSIONS:
            self.context.set_status("Avatar must be a PNG or JPG file.", duration=3.0)
            return
        try:
            source = pygame.image.load(str(path)).convert_alpha()
        except pygame.error as err:
            self.context.set_status(f"Could not load avatar image: {err}", duration=4.0)
            return

        self._editing_source = source
        self._editing_source_name = path.name
        self._crop_zoom = 1.0
        self._crop_offset.update(0, 0)
        self._dragging_crop = False

    def _use_default_avatar(self):
        self.context.avatar_surface = None
        self.context.avatar_window_surface = None
        self.context.avatar_source_name = "Default avatar"
        self._refresh_previews()
        self.context.set_status("Avatar reset to default.", duration=2.0)

    def _cover_scale(self, target_size: int, source: pygame.Surface) -> float:
        return max(target_size / source.get_width(), target_size / source.get_height()) * self._crop_zoom

    def _clamp_crop_offset(self):
        source = self._editing_source
        if source is None:
            self._crop_offset.update(0, 0)
            return
        scale = self._cover_scale(self._crop_rect.w, source)
        scaled_w = source.get_width() * scale
        scaled_h = source.get_height() * scale
        max_x = max(0, (scaled_w - self._crop_rect.w) / 2)
        max_y = max(0, (scaled_h - self._crop_rect.h) / 2)
        self._crop_offset.x = max(-max_x, min(max_x, self._crop_offset.x))
        self._crop_offset.y = max(-max_y, min(max_y, self._crop_offset.y))

    def _set_crop_zoom(self, zoom: float):
        self._crop_zoom = max(1.0, min(4.0, zoom))
        self._clamp_crop_offset()

    def _render_crop_surface(self, size: int) -> pygame.Surface | None:
        source = self._editing_source
        if source is None:
            return None
        output = pygame.Surface((size, size), pygame.SRCALPHA)
        scale = self._cover_scale(size, source)
        scaled_size = (
            max(1, int(round(source.get_width() * scale))),
            max(1, int(round(source.get_height() * scale))),
        )
        scaled = pygame.transform.smoothscale(source, scaled_size)
        offset_scale = size / self._crop_rect.w
        rect = scaled.get_rect(
            center=(
                size // 2 + int(round(self._crop_offset.x * offset_scale)),
                size // 2 + int(round(self._crop_offset.y * offset_scale)),
            )
        )
        output.blit(scaled, rect)
        return output

    def _apply_crop(self):
        cropped = self._render_crop_surface(256)
        if cropped is None:
            return
        self.context.avatar_window_surface = cropped
        self.context.avatar_surface = prepare_avatar(cropped)
        self.context.avatar_source_name = self._editing_source_name
        self._editing_source = None
        self._dragging_crop = False
        self._refresh_previews()
        self.context.set_status("Avatar updated.", duration=2.0)

    def handle_event(self, event):
        super().handle_event(event)
        if self._editing_source is not None:
            self._handle_crop_event(event)
            return
        self._layout()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.switch("menu")
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.back_button.rect.collidepoint(event.pos):
                self.switch("menu")
                return
            if self.upload_button.rect.collidepoint(event.pos):
                self._upload_avatar()
                return
            if self.default_button.rect.collidepoint(event.pos):
                self._use_default_avatar()

    def update(self, dt: float):
        _ = dt
        if self._editing_source is not None:
            self._crop_layout()
            mp = self.context.mouse_pos
            self._save_h = self.save_crop_button.rect.collidepoint(mp)
            self._cancel_h = self.cancel_crop_button.rect.collidepoint(mp)
            self._zoom_in_h = self.zoom_in_button.rect.collidepoint(mp)
            self._zoom_out_h = self.zoom_out_button.rect.collidepoint(mp)
            return
        self._layout()
        mp = self.context.mouse_pos
        self._back_h = self.back_button.rect.collidepoint(mp)
        self._upload_h = self.upload_button.rect.collidepoint(mp)
        self._default_h = self.default_button.rect.collidepoint(mp)

    def draw(self, surface):
        super().draw(surface)
        if self._editing_source is not None:
            self._draw_crop_editor(surface)
            return
        self._layout()
        theme = DEFAULT_THEME
        width, height = surface.get_size()

        ui.draw_button(surface, self.context.small_font, self.back_button, theme, hovered=self._back_h, variant="neutral")
        title = self.context.title_font.render("Avatar", True, theme.text)
        surface.blit(title, title.get_rect(center=(width // 2, 42)))

        preview_y = max(76, height // 2 - 100)
        preview = self._make_player_preview(6)
        if preview is not None:
            surface.blit(preview, preview.get_rect(center=(width // 2 - 120, preview_y + 96)))
        else:
            missing = self.context.small_font.render("Preview unavailable", True, theme.text_warn)
            surface.blit(missing, missing.get_rect(center=(width // 2 - 120, preview_y + 96)))

        crop_label = self.context.small_font.render("1:1 Crop", True, theme.text)
        crop_center = (width // 2 + 120, preview_y + 78)
        surface.blit(crop_label, crop_label.get_rect(center=(crop_center[0], preview_y + 8)))
        if self._crop_preview is not None:
            crop_rect = self._crop_preview.get_rect(center=crop_center)
            surface.blit(self._crop_preview, crop_rect)
            pygame.draw.rect(surface, theme.border_focus, crop_rect, width=2, border_radius=4)

        source = self.context.tiny_font.render(self.context.avatar_source_name, True, theme.text_muted)
        surface.blit(source, source.get_rect(center=(width // 2 + 120, preview_y + 150)))

        ui.draw_button(surface, self.context.small_font, self.upload_button, theme, hovered=self._upload_h)
        ui.draw_button(surface, self.context.small_font, self.default_button, theme, hovered=self._default_h, variant="neutral")

    def _make_player_preview(self, scale: int) -> pygame.Surface | None:
        if self._idle_body_frame is None:
            return None
        preview = pygame.Surface((PLAYER_FRAME_WIDTH * scale, PLAYER_FRAME_HEIGHT * scale), pygame.SRCALPHA)
        avatar_source = self._current_crop_source()
        avatar_rect = pygame.Rect(
            AVATAR_RECT.x * scale,
            AVATAR_RECT.y * scale,
            AVATAR_RECT.w * scale,
            AVATAR_RECT.h * scale,
        )
        avatar = pygame.transform.smoothscale(crop_square(avatar_source), avatar_rect.size)
        body = pygame.transform.scale(self._idle_body_frame, preview.get_size())
        preview.blit(avatar, avatar_rect)
        preview.blit(body, (0, 0))
        return preview

    def _handle_crop_event(self, event):
        self._crop_layout()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._editing_source = None
            self._dragging_crop = False
            return
        if event.type == pygame.MOUSEWHEEL:
            self._set_crop_zoom(self._crop_zoom + 0.12 * event.y)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.save_crop_button.rect.collidepoint(event.pos):
                self._apply_crop()
                return
            if self.cancel_crop_button.rect.collidepoint(event.pos):
                self._editing_source = None
                self._dragging_crop = False
                return
            if self.zoom_in_button.rect.collidepoint(event.pos):
                self._set_crop_zoom(self._crop_zoom + 0.15)
                return
            if self.zoom_out_button.rect.collidepoint(event.pos):
                self._set_crop_zoom(self._crop_zoom - 0.15)
                return
            if self._crop_rect.collidepoint(event.pos):
                self._dragging_crop = True
                self._last_drag_pos.update(event.pos)
                return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging_crop = False
            return
        if event.type == pygame.MOUSEMOTION and self._dragging_crop:
            current = pygame.Vector2(event.pos)
            self._crop_offset += current - self._last_drag_pos
            self._last_drag_pos = current
            self._clamp_crop_offset()

    def _draw_crop_editor(self, surface):
        self._crop_layout()
        theme = DEFAULT_THEME
        width, _height = surface.get_size()
        title = self.context.title_font.render("Crop Avatar", True, theme.text)
        surface.blit(title, title.get_rect(center=(width // 2, 36)))

        cropped = self._render_crop_surface(self._crop_rect.w)
        if cropped is not None:
            surface.blit(cropped, self._crop_rect)
        pygame.draw.rect(surface, theme.border_focus, self._crop_rect, width=2, border_radius=4)

        ui.draw_button(surface, self.context.font, self.zoom_in_button, theme, hovered=self._zoom_in_h, variant="neutral")
        ui.draw_button(surface, self.context.font, self.zoom_out_button, theme, hovered=self._zoom_out_h, variant="neutral")
        ui.draw_button(surface, self.context.small_font, self.save_crop_button, theme, hovered=self._save_h)
        ui.draw_button(surface, self.context.small_font, self.cancel_crop_button, theme, hovered=self._cancel_h, variant="neutral")
