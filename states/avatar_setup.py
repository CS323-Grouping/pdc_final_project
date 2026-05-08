from pathlib import Path

import pygame

from network import protocol
from player_scripts.avatar_sprite import AVATAR_RECT, VALID_AVATAR_EXTENSIONS, crop_square
from player_scripts.model_assets import load_body_variation_frame, load_default_head_texture
from states.common import ScreenState
from ui import components as ui
from ui.theme import DEFAULT_THEME
from world.constants import PLAYER_FRAME_HEIGHT, PLAYER_FRAME_WIDTH


EDIT_AVATAR_RECTS = {
    "preview_section": pygame.Rect(24, 24, 92, 132),
    "model_frame": pygame.Rect(35, 36, 70, 80),
    "model_background": pygame.Rect(37, 38, 66, 76),
    "upload": pygame.Rect(31, 124, 37, 24),
    "remove": pygame.Rect(72, 124, 37, 24),
    "option_section": pygame.Rect(120, 24, 176, 92),
    "option_title": pygame.Rect(132, 32, 152, 14),
    "save": pygame.Rect(127, 124, 78, 24),
    "cancel": pygame.Rect(211, 124, 78, 24),
}

EDIT_AVATAR_OPTION_COLORS = ("Black", "Blue", "Gray", "Green", "Purple", "Red", "White")
OPTION_TEXTURE_SIZE = (20, 17)
PLAYER_PREVIEW_SCALE = 1.875
PLAYER_PREVIEW_SIZE = (
    int(round(PLAYER_FRAME_WIDTH * PLAYER_PREVIEW_SCALE)),
    int(round(PLAYER_FRAME_HEIGHT * PLAYER_PREVIEW_SCALE)),
)
HEAD_PREVIEW_SIZE = 26
HEAD_PREVIEW_OFFSET_X = 1


class AvatarSetupState(ScreenState):
    render_to_internal = True
    suppress_internal_global_messages = True

    def __init__(self, machine, context, **kwargs):
        super().__init__(machine, context, **kwargs)
        self.save_crop_button = ui.Button(pygame.Rect(0, 0, 130, 38), "Save Crop")
        self.cancel_crop_button = ui.Button(pygame.Rect(0, 0, 110, 38), "Cancel")
        self.zoom_in_button = ui.Button(pygame.Rect(0, 0, 42, 38), "+")
        self.zoom_out_button = ui.Button(pygame.Rect(0, 0, 42, 38), "-")

        self._assets: dict[str, pygame.Surface] = {}
        self._window_fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self._hovered: str | None = None
        self._pending_dialog: str | None = None

        self._draft_model_color = protocol.DEFAULT_MODEL_COLOR
        self._draft_avatar_source: pygame.Surface | None = None
        self._draft_avatar_source_name = "Default head"
        self._draft_use_custom_head = False
        self._draft_head_changed = False
        self._body_frame: pygame.Surface | None = None

        self._save_h = False
        self._cancel_h = False
        self._zoom_in_h = False
        self._zoom_out_h = False
        self._editing_source: pygame.Surface | None = None
        self._editing_source_name = ""
        self._crop_zoom = 1.0
        self._crop_offset = pygame.Vector2(0, 0)
        self._crop_rect = pygame.Rect(0, 0, 220, 220)
        self._dragging_crop = False
        self._last_drag_pos = pygame.Vector2(0, 0)

    def enter(self):
        self._assets = self._load_assets()
        self._reset_draft_from_context()

    def _load_assets(self) -> dict[str, pygame.Surface]:
        edit_root = self.context.project_root / "assets" / "editAvatar"
        menu_root = self.context.project_root / "assets" / "Menu"
        names = {
            "background": menu_root / "MenuBackground_Image.png",
            "preview_section": edit_root / "EditAvatarPreviewSection_Frame.png",
            "model_frame": edit_root / "EditAvatarPreviewSectionModel_Frame.png",
            "model_background": edit_root / "EditAvatarPreviewSectionModelFrame_Background.png",
            "upload": edit_root / "EditAvatarPreviewSectionUpload_Button.png",
            "upload_icon": edit_root / "EditAvatarPreviewSectionUpload_ButtonIcon.png",
            "remove": edit_root / "EditAvatarPreviewSectionRemove_Button.png",
            "remove_disabled": edit_root / "EditAvatarPreviewSectionRemove_ButtonDisabled.png",
            "remove_icon": edit_root / "EditAvatarPreviewSectionRemove_ButtonIcon.png",
            "remove_icon_disabled": edit_root / "EditAvatarPreviewSectionRemove_ButtonIconDisabled.png",
            "option_section": edit_root / "EditAvatarOptionSection_Frame.png",
            "option": edit_root / "EditAvatarOptionSectionOption_Frame.png",
            "option_textures": edit_root / "EditAvatarOptionSectionOptionColor_Textures.png",
            "save": edit_root / "EditAvatarOptionSectionSave_Button.png",
            "save_disabled": edit_root / "EditAvatarOptionSectionSave_ButtonDisabled.png",
            "cancel": edit_root / "EditAvatarOptionSectionCancel_Button.png",
            "dialog_frame": edit_root / "EditAvatarDiscardRemoveConfirmation_Window.png",
            "dialog_confirm": edit_root / "EditAvatarDiscardRemoveConfirmationWindowConfirm_Button.png",
            "dialog_cancel": edit_root / "EditAvatarDiscardRemoveConfirmationWindowCancel_Button.png",
            "crop_window": edit_root / "EditAvatarCropImageWindow_Frame.png",
            "crop_preview": edit_root / "EditAvatarCropImagePreview_Frame.png",
            "crop_save": edit_root / "EditAvatarCropImageSave_Button.png",
            "crop_cancel": edit_root / "EditAvatarCropImageCancel_Button.png",
            "crop_zoom": edit_root / "EditAvatarCropImageZoomInOut_Button.png",
        }
        assets: dict[str, pygame.Surface] = {}
        for key, path in names.items():
            try:
                assets[key] = pygame.image.load(str(path)).convert_alpha()
            except (FileNotFoundError, pygame.error):
                fallback = pygame.Surface((16, 16), pygame.SRCALPHA)
                fallback.fill((25, 38, 58, 255))
                assets[key] = fallback
        return assets

    def _reset_draft_from_context(self):
        self._draft_model_color = protocol.normalize_model_color(self.context.model_color)
        self._draft_avatar_source = self.context.current_avatar_source().copy()
        self._draft_avatar_source_name = self.context.avatar_source_name
        self._draft_use_custom_head = self.context.use_custom_head
        self._draft_head_changed = False
        self._pending_dialog = None
        self._load_body_frame()

    def _load_body_frame(self):
        self._body_frame = load_body_variation_frame(
            self.context.project_root,
            self.context.model_type,
            self._draft_model_color,
        )

    def _has_unsaved_changes(self) -> bool:
        return (
            self._draft_head_changed
            or self._draft_use_custom_head != self.context.use_custom_head
            or self._draft_model_color != protocol.normalize_model_color(self.context.model_color)
        )

    def _can_remove_head(self) -> bool:
        return self._draft_use_custom_head

    def _default_head_source(self) -> pygame.Surface:
        return load_default_head_texture(self.context.project_root)

    def _discard_changes(self):
        self._reset_draft_from_context()
        self.switch("menu")

    def _remove_uploaded_head(self):
        self._draft_avatar_source = self._default_head_source()
        self._draft_avatar_source_name = "Default head"
        self._draft_use_custom_head = False
        self._draft_head_changed = True
        self._pending_dialog = None

    def _save_changes(self):
        if not self._has_unsaved_changes():
            return
        self.context.set_model_color(self._draft_model_color, save=False)
        if self._draft_use_custom_head:
            if self._draft_avatar_source is not None and self._draft_head_changed:
                self.context.cache_custom_head(self._draft_avatar_source, self._draft_avatar_source_name)
            else:
                self.context.save_profile()
        else:
            self.context.use_default_head(save=False)
            self.context.save_profile()
        self._reset_draft_from_context()
        self.context.set_status("Avatar saved.", duration=2.0)

    def _handle_cancel_or_back(self):
        if self._has_unsaved_changes():
            self._pending_dialog = "discard"
        else:
            self.switch("menu")

    def _dialog_layout(self) -> dict[str, pygame.Rect]:
        frame_asset = self._assets.get("dialog_frame")
        confirm_asset = self._assets.get("dialog_confirm")
        frame_w, frame_h = frame_asset.get_size() if frame_asset is not None else (148, 84)
        button_w, button_h = confirm_asset.get_size() if confirm_asset is not None else (64, 24)
        frame = pygame.Rect((320 - frame_w) // 2, (180 - frame_h) // 2, frame_w, frame_h)
        confirm = pygame.Rect(frame.x + 7, frame.bottom - 7 - button_h, button_w, button_h)
        cancel = pygame.Rect(frame.right - 7 - button_w, confirm.y, button_w, button_h)
        return {
            "frame": frame,
            "title": pygame.Rect(frame.x + 7, frame.y + 15, frame.w - 14, 16),
            "body": pygame.Rect(frame.x + 7, frame.y + 34, frame.w - 14, 18),
            "confirm": confirm,
            "cancel": cancel,
        }

    def _option_rects(self) -> list[tuple[str, pygame.Rect, pygame.Rect]]:
        rects: list[tuple[str, pygame.Rect, pygame.Rect]] = []
        start_x = EDIT_AVATAR_RECTS["option_section"].x + 12
        start_y = EDIT_AVATAR_RECTS["option_title"].bottom + 4
        frame_w, frame_h = self._assets["option"].get_size()
        for index, color in enumerate(EDIT_AVATAR_OPTION_COLORS):
            col = index % 5
            row = index // 5
            frame = pygame.Rect(start_x + col * (frame_w + 3), start_y + row * (frame_h + 4), frame_w, frame_h)
            texture = pygame.Rect(0, 0, OPTION_TEXTURE_SIZE[0], OPTION_TEXTURE_SIZE[1])
            texture.center = frame.center
            rects.append((color, frame, texture))
        return rects

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

    def _crop_layout(self) -> dict[str, pygame.Rect]:
        frame_asset = self._assets.get("crop_window")
        preview_asset = self._assets.get("crop_preview")
        save_asset = self._assets.get("crop_save")
        zoom_asset = self._assets.get("crop_zoom")
        frame_w, frame_h = frame_asset.get_size() if frame_asset is not None else (148, 102)
        preview_w, preview_h = preview_asset.get_size() if preview_asset is not None else (50, 50)
        save_w, save_h = save_asset.get_size() if save_asset is not None else (64, 24)
        zoom_w, zoom_h = zoom_asset.get_size() if zoom_asset is not None else (24, 24)

        frame = pygame.Rect((320 - frame_w) // 2, (180 - frame_h) // 2, frame_w, frame_h)
        preview_frame = pygame.Rect(frame.x + 13, frame.y + 13, preview_w, preview_h)
        self._crop_rect = preview_frame.inflate(-4, -4)

        zoom_y = frame.y + 40
        self.zoom_in_button.rect = pygame.Rect(frame.x + 80, zoom_y, zoom_w, zoom_h)
        self.zoom_out_button.rect = pygame.Rect(frame.x + 112, zoom_y, zoom_w, zoom_h)
        self.save_crop_button.rect = pygame.Rect(frame.x + 7, frame.bottom - 7 - save_h, save_w, save_h)
        self.cancel_crop_button.rect = pygame.Rect(frame.right - 7 - save_w, frame.bottom - 7 - save_h, save_w, save_h)
        return {
            "frame": frame,
            "preview_frame": preview_frame,
            "crop": self._crop_rect,
            "zoom_in": self.zoom_in_button.rect,
            "zoom_out": self.zoom_out_button.rect,
            "save": self.save_crop_button.rect,
            "cancel": self.cancel_crop_button.rect,
        }

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
        self._draft_avatar_source = cropped
        self._draft_avatar_source_name = self._editing_source_name
        self._draft_use_custom_head = True
        self._draft_head_changed = True
        self._editing_source = None
        self._dragging_crop = False
        self.context.set_status("Avatar image staged.", duration=2.0)

    def handle_event(self, event):
        super().handle_event(event)
        if self._editing_source is not None:
            self._handle_crop_event(event)
            return
        if self._pending_dialog is not None:
            self._handle_dialog_event(event)
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._handle_cancel_or_back()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if EDIT_AVATAR_RECTS["upload"].collidepoint(event.pos):
                self._upload_avatar()
                return
            if EDIT_AVATAR_RECTS["remove"].collidepoint(event.pos):
                if self._can_remove_head():
                    self._pending_dialog = "remove"
                return
            if EDIT_AVATAR_RECTS["save"].collidepoint(event.pos):
                self._save_changes()
                return
            if EDIT_AVATAR_RECTS["cancel"].collidepoint(event.pos):
                self._handle_cancel_or_back()
                return
            for color, frame, _texture in self._option_rects():
                if frame.collidepoint(event.pos):
                    self._draft_model_color = color
                    self._load_body_frame()
                    return

    def _handle_dialog_event(self, event):
        layout = self._dialog_layout()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._pending_dialog = None
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if layout["cancel"].collidepoint(event.pos):
            self._pending_dialog = None
            return
        if layout["confirm"].collidepoint(event.pos):
            if self._pending_dialog == "remove":
                self._remove_uploaded_head()
            elif self._pending_dialog == "discard":
                self._discard_changes()
            return

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
        if self._pending_dialog is not None:
            mp = self.context.mouse_pos
            dialog = self._dialog_layout()
            if dialog["confirm"].collidepoint(mp):
                self._hovered = "dialog_confirm"
            elif dialog["cancel"].collidepoint(mp):
                self._hovered = "dialog_cancel"
            else:
                self._hovered = None
            return
        mp = self.context.mouse_pos
        self._hovered = None
        for key in ("upload", "remove", "save", "cancel"):
            if EDIT_AVATAR_RECTS[key].collidepoint(mp):
                self._hovered = key
                return
        for color, frame, _texture in self._option_rects():
            if frame.collidepoint(mp):
                self._hovered = f"color:{color}"
                return

    def draw(self, surface):
        if self._editing_source is not None:
            self._draw_crop_editor(surface)
            return
        background = self._assets.get("background")
        if background is not None:
            surface.blit(background, (0, 0))
        else:
            surface.fill(DEFAULT_THEME.bg)

        self._draw_asset(surface, "preview_section", EDIT_AVATAR_RECTS["preview_section"])
        self._draw_asset(surface, "option_section", EDIT_AVATAR_RECTS["option_section"])
        self._draw_asset(surface, "model_background", EDIT_AVATAR_RECTS["model_background"])
        self._draw_player_preview(surface)
        self._draw_asset(surface, "model_frame", EDIT_AVATAR_RECTS["model_frame"])

        self._draw_button_with_icon(surface, "upload", "upload_icon", EDIT_AVATAR_RECTS["upload"])
        remove_enabled = self._can_remove_head()
        remove_asset = "remove" if remove_enabled else "remove_disabled"
        remove_icon = "remove_icon" if remove_enabled else "remove_icon_disabled"
        self._draw_button_with_icon(surface, remove_asset, remove_icon, EDIT_AVATAR_RECTS["remove"])

        self._draw_color_options(surface)
        save_asset = "save" if self._has_unsaved_changes() else "save_disabled"
        self._draw_asset(surface, save_asset, EDIT_AVATAR_RECTS["save"])
        self._draw_asset(surface, "cancel", EDIT_AVATAR_RECTS["cancel"])
        self._draw_hover_outlines(surface)

        if self._pending_dialog is not None:
            self._draw_dim_overlay(surface)
            self._draw_dialog(surface)

    def _draw_crop_editor(self, surface):
        layout = self._crop_layout()
        background = self._assets.get("background")
        if background is not None:
            surface.blit(background, (0, 0))
        else:
            surface.fill(DEFAULT_THEME.bg)
        self._draw_dim_overlay(surface)
        self._draw_asset(surface, "crop_window", layout["frame"])
        self._draw_asset(surface, "crop_preview", layout["preview_frame"])
        self._draw_asset(surface, "crop_zoom", layout["zoom_in"])
        self._draw_asset(surface, "crop_zoom", layout["zoom_out"])
        self._draw_asset(surface, "crop_save", layout["save"])
        self._draw_asset(surface, "crop_cancel", layout["cancel"])
        self._draw_crop_hover_outlines(surface)

    def _draw_asset(self, surface: pygame.Surface, key: str, rect: pygame.Rect):
        asset = self._assets.get(key)
        if asset is not None:
            surface.blit(pygame.transform.scale(asset, rect.size), rect)

    def _draw_window_asset(self, surface: pygame.Surface, key: str, rect: pygame.Rect):
        asset = self._assets.get(key)
        if asset is not None:
            scaled_rect = self._scale_rect(rect)
            surface.blit(pygame.transform.scale(asset, scaled_rect.size), scaled_rect)

    def _draw_button_with_icon(self, surface: pygame.Surface, button_key: str, icon_key: str, rect: pygame.Rect):
        self._draw_asset(surface, button_key, rect)
        icon = self._assets.get(icon_key)
        if icon is None:
            return
        icon_rect = icon.get_rect(center=rect.center)
        surface.blit(icon, icon_rect)

    def _player_preview_rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, *PLAYER_PREVIEW_SIZE)
        rect.center = EDIT_AVATAR_RECTS["model_frame"].center
        return rect

    def _head_preview_rect(self) -> pygame.Rect:
        model_rect = self._player_preview_rect()
        return pygame.Rect(
            model_rect.x + int(round(AVATAR_RECT.x * PLAYER_PREVIEW_SCALE)) + HEAD_PREVIEW_OFFSET_X,
            model_rect.y + int(round(AVATAR_RECT.y * PLAYER_PREVIEW_SCALE)),
            HEAD_PREVIEW_SIZE,
            HEAD_PREVIEW_SIZE,
        )

    def _draw_player_preview(self, surface: pygame.Surface):
        if self._body_frame is None or self._draft_avatar_source is None:
            return
        body = pygame.transform.scale(self._body_frame, PLAYER_PREVIEW_SIZE)
        head = pygame.transform.scale(crop_square(self._draft_avatar_source), (HEAD_PREVIEW_SIZE, HEAD_PREVIEW_SIZE))
        model = pygame.Surface(PLAYER_PREVIEW_SIZE, pygame.SRCALPHA)
        head_pos = self._head_preview_rect()
        model_rect = self._player_preview_rect()
        head_pos = (head_pos.x - model_rect.x, head_pos.y - model_rect.y)
        model.blit(head, head_pos)
        model.blit(body, (0, 0))
        surface.blit(model, model_rect)

    def _draw_window_player_preview(self, surface: pygame.Surface):
        if self._body_frame is None or self._draft_avatar_source is None:
            return
        model_rect = self._scale_rect(self._player_preview_rect())
        head_rect = self._scale_rect(self._head_preview_rect())
        head = pygame.transform.smoothscale(crop_square(self._draft_avatar_source), head_rect.size)
        body = pygame.transform.scale(self._body_frame, model_rect.size)
        surface.blit(head, head_rect)
        surface.blit(body, model_rect)

    def _draw_window_crop_preview(self, surface: pygame.Surface):
        layout = self._crop_layout()
        crop_rect = self._scale_rect(self._crop_rect)
        cropped = self._render_crop_surface(crop_rect.w)
        if cropped is not None:
            surface.blit(cropped, crop_rect)
        self._draw_window_asset(surface, "crop_preview", layout["preview_frame"])

    def _draw_color_options(self, surface: pygame.Surface):
        option_frame = self._assets.get("option")
        texture_strip = self._assets.get("option_textures")
        for index, (color, frame, texture_rect) in enumerate(self._option_rects()):
            if option_frame is not None:
                surface.blit(option_frame, frame)
            if texture_strip is not None:
                source = pygame.Rect(index * OPTION_TEXTURE_SIZE[0], 0, OPTION_TEXTURE_SIZE[0], OPTION_TEXTURE_SIZE[1])
                surface.blit(texture_strip, texture_rect, source)
            if color == self._draft_model_color:
                pygame.draw.rect(surface, (115, 190, 255), frame.inflate(2, 2), width=1, border_radius=2)

    def _draw_hover_outlines(self, surface: pygame.Surface):
        if self._hovered is None:
            return
        if self._hovered == "save" and not self._has_unsaved_changes():
            return
        if self._hovered == "remove" and not self._can_remove_head():
            return
        rect = None
        if self._hovered in EDIT_AVATAR_RECTS:
            rect = EDIT_AVATAR_RECTS[self._hovered]
        elif self._hovered.startswith("color:"):
            color_name = self._hovered.split(":", 1)[1]
            for color, frame, _texture in self._option_rects():
                if color == color_name:
                    rect = frame
                    break
        elif self._hovered in ("dialog_confirm", "dialog_cancel"):
            layout = self._dialog_layout()
            rect = layout["confirm" if self._hovered == "dialog_confirm" else "cancel"]
        if rect is not None:
            pygame.draw.rect(surface, (115, 190, 255), rect.inflate(2, 2), width=1, border_radius=2)

    def _draw_crop_hover_outlines(self, surface: pygame.Surface):
        for rect, hovered in (
            (self.zoom_in_button.rect, self._zoom_in_h),
            (self.zoom_out_button.rect, self._zoom_out_h),
            (self.save_crop_button.rect, self._save_h),
            (self.cancel_crop_button.rect, self._cancel_h),
        ):
            if hovered:
                pygame.draw.rect(surface, (115, 190, 255), rect.inflate(2, 2), width=1, border_radius=2)

    def _draw_dim_overlay(self, surface: pygame.Surface):
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 135))
        surface.blit(overlay, (0, 0))

    def _draw_dialog(self, surface: pygame.Surface):
        layout = self._dialog_layout()
        self._draw_asset(surface, "dialog_frame", layout["frame"])
        self._draw_asset(surface, "dialog_confirm", layout["confirm"])
        self._draw_asset(surface, "dialog_cancel", layout["cancel"])
        self._draw_hover_outlines(surface)

    def _window_scale(self) -> int:
        if self.context.display_manager is None:
            return 1
        return self.context.display_manager.config.selected_scale

    def _scale_rect(self, rect: pygame.Rect) -> pygame.Rect:
        scale = self._window_scale()
        return pygame.Rect(rect.x * scale, rect.y * scale, rect.w * scale, rect.h * scale)

    def _window_font(self, logical_size: int, bold: bool = True) -> pygame.font.Font:
        scale = self._window_scale()
        size = max(10, logical_size * scale)
        key = (size, bold)
        font = self._window_fonts.get(key)
        if font is None:
            font = pygame.font.SysFont("consolas", size, bold=bold)
            self._window_fonts[key] = font
        return font

    def _draw_text_center(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        bold: bool = True,
        shadow: bool = True,
    ):
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size, bold=bold)
        if shadow:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, shade.get_rect(center=(rect.centerx + scale, rect.centery + scale)))
        label = font.render(text, True, color)
        surface.blit(label, label.get_rect(center=rect.center))

    def draw_window_overlay(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        if self._editing_source is None:
            if self._pending_dialog is None:
                self._draw_window_player_preview(surface)
                self._draw_text_center(surface, 7, "MODEL COLOR", EDIT_AVATAR_RECTS["option_title"], (180, 220, 255))
                save_color = theme.text if self._has_unsaved_changes() else theme.text_muted
                self._draw_text_center(surface, 7, "SAVE", EDIT_AVATAR_RECTS["save"], save_color)
                cancel_label = "CANCEL" if self._has_unsaved_changes() else "BACK"
                self._draw_text_center(surface, 7, cancel_label, EDIT_AVATAR_RECTS["cancel"], theme.text)
            else:
                layout = self._dialog_layout()
                if self._pending_dialog == "remove":
                    title = "Remove Image?"
                    body = "This will remove the uploaded image"
                else:
                    title = "Discard Changes?"
                    body = "Changes will not be saved"
                self._draw_text_center(surface, 7, title, layout["title"], theme.text)
                self._draw_text_center(surface, 5, body, layout["body"], theme.text_muted)
                self._draw_text_center(surface, 7, "CONFIRM", layout["confirm"], theme.text)
                self._draw_text_center(surface, 7, "CANCEL", layout["cancel"], theme.text)
        else:
            self._crop_layout()
            self._draw_window_crop_preview(surface)
            self._draw_text_center(surface, 8, "+", self.zoom_in_button.rect, theme.text)
            self._draw_text_center(surface, 8, "-", self.zoom_out_button.rect, theme.text)
            self._draw_text_center(surface, 7, "SAVE", self.save_crop_button.rect, theme.text)
            self._draw_text_center(surface, 7, "CANCEL", self.cancel_crop_button.rect, theme.text)
        self.context.draw_global_messages(surface)
