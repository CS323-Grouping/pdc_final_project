from dataclasses import dataclass
import math
import time
import zlib

import pygame

from app.config import LobbyPlayerStatus, lobby_player_status
from network import network_handler as nw
from network import protocol
from player_scripts.animation import load_spritesheet_frames
from player_scripts.avatar_sprite import AVATAR_RECT, crop_square, make_default_avatar
from player_scripts.model_assets import animation_path
from ui.theme import DEFAULT_THEME
from world.constants import INTERNAL_HEIGHT, INTERNAL_WIDTH, PLAYER_FRAME_HEIGHT, PLAYER_FRAME_WIDTH


ROOM_LOBBY_RECTS = {
    "background": pygame.Rect(0, 0, INTERNAL_WIDTH, INTERNAL_HEIGHT),
    "screen": pygame.Rect(24, 32, 272, 102),
    "room_name": pygame.Rect(31, 14, 129, 18),
    "player_count": pygame.Rect(239, 14, 50, 18),
}

PLAYER_CARD_RECTS = tuple(
    pygame.Rect(31 + index * 52, 40, 50, 86)
    for index in range(protocol.MAX_PLAYERS)
)

BUTTON_Y = ROOM_LOBBY_RECTS["screen"].bottom + 8
LOBBY_BUTTON_SIZE = (78, 24)
KICK_MODE_BUTTON_SIZE = (24, 24)
BUTTON_GAP = 8


@dataclass
class AvatarAssembly:
    total_chunks: int
    payload_size: int = 0
    chunks: dict[int, bytes] = None

    def __post_init__(self):
        if self.chunks is None:
            self.chunks = {}


class RoomLobbyUi:
    def __init__(self, context):
        self.context = context
        self._assets: dict[str, pygame.Surface] = {}
        self._window_fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self._idle_body_frame: pygame.Surface | None = None
        self._body_frame_cache: dict[tuple[str, str], pygame.Surface] = {}
        self._remote_avatar_surfaces: dict[int, pygame.Surface] = {}
        self._remote_models: dict[int, tuple[str, str]] = {}
        self._avatar_assemblies: dict[tuple[int, int], AvatarAssembly] = {}
        self._avatar_payload: bytes | None = None
        self._avatar_id = 0
        self._avatar_send_timer = 0.0
        self._avatar_send_count = 0

    def enter(self):
        self._assets = self._load_assets()
        self._load_player_preview_frame()
        self._body_frame_cache.clear()
        self._remote_avatar_surfaces.clear()
        self._remote_models.clear()
        self._avatar_assemblies.clear()
        self._avatar_payload = self._make_avatar_payload()
        self._avatar_id = zlib.adler32(self._avatar_payload) & 0xFFFF if self._avatar_payload else 0
        self._avatar_send_timer = 0.0
        self._avatar_send_count = 0

    def _load_assets(self) -> dict[str, pygame.Surface]:
        root = self.context.project_root / "assets" / "roomLobby"
        menu_root = self.context.project_root / "assets" / "Menu"
        names = {
            "background": menu_root / "MenuBackground_Image.png",
            "screen": root / "RoomLobbyScreen_Frame.png",
            "room_name": root / "RoomLobbyScreenRoomName_Frame.png",
            "player_count": root / "RoomLobbyScreenPlayerCount_Frame.png",
            "player_card": root / "RoomLobbyScreenPlayerCard_Frame.png",
            "player_model": root / "RoomLobbyScreenPlayer_Model.png",
            "player_platform": root / "RoomLobbyScreenPlayerModel_Platform.png",
            "status_host": root / "RoomLobbyScreenPlayerStatusHost_Frame.png",
            "status_ready": root / "RoomLobbyScreenPlayerStatusReady_Frame.png",
            "status_waiting": root / "RoomLobbyScreenPlayerStatusWaiting_Frame.png",
            "ready_start": root / "RoomLobbyScreenReadyStart_Button.png",
            "ready_start_disabled": root / "RoomLobbyScreenReadyStart_ButtonDisabled.png",
            "leave": root / "RoomLobbyScreenLeave_Button.png",
            "host_close": root / "RoomLobbyScreenHostCloseRoom_Button.png",
            "kick_mode_off": root / "RoomLobbyScreenHostKickModeOff_Button.png",
            "kick_mode_off_icon": root / "RoomLobbyScreenHostKickModeOff_Icon.png",
            "kick_mode_on": root / "RoomLobbyScreenHostKickModeOn_Button.png",
            "kick_mode_on_icon": root / "RoomLobbyScreenHostKickModeOn_Icon.png",
            "kick_player": root / "RoomLobbyScreenHostKickPlayer_Button.png",
            "starting_window": root / "RoomLobbyStartingWindow_Frame.png",
            "close_confirmation_window": root / "RoomLobbyCloseConfirmationWindow_Frame.png",
            "close_confirmation_close": root / "RoomLobbyCloseConfirmationWindowClose_Button.png",
            "close_confirmation_cancel": root / "RoomLobbyCloseConfirmationWindowCancel_Button.png",
            "room_name_edit_frame": root / "RoomNameEditWindow_Frame.png",
            "room_name_edit_field": root / "RoomNameEditWindowNameField_Frame.png",
            "room_name_edit_save": root / "RoomNameEditWindowSave_Button.png",
            "room_name_edit_save_disabled": root / "RoomNameEditWindowSave_ButtonDisabled.png",
            "room_name_edit_cancel": root / "RoomNameEditWindowCancel_Button.png",
        }
        fallbacks = {
            "background": ROOM_LOBBY_RECTS["background"].size,
            "screen": ROOM_LOBBY_RECTS["screen"].size,
            "room_name": ROOM_LOBBY_RECTS["room_name"].size,
            "player_count": ROOM_LOBBY_RECTS["player_count"].size,
            "player_card": PLAYER_CARD_RECTS[0].size,
            "player_model": (22, 32),
            "player_platform": (30, 17),
            "status_host": (36, 14),
            "status_ready": (36, 14),
            "status_waiting": (36, 14),
            "ready_start": LOBBY_BUTTON_SIZE,
            "ready_start_disabled": LOBBY_BUTTON_SIZE,
            "leave": LOBBY_BUTTON_SIZE,
            "host_close": LOBBY_BUTTON_SIZE,
            "kick_mode_off": KICK_MODE_BUTTON_SIZE,
            "kick_mode_off_icon": (12, 12),
            "kick_mode_on": KICK_MODE_BUTTON_SIZE,
            "kick_mode_on_icon": (12, 12),
            "kick_player": (36, 14),
            "starting_window": (148, 84),
            "close_confirmation_window": (148, 84),
            "close_confirmation_close": (64, 24),
            "close_confirmation_cancel": (64, 24),
            "room_name_edit_frame": (148, 84),
            "room_name_edit_field": (134, 18),
            "room_name_edit_save": (64, 24),
            "room_name_edit_save_disabled": (64, 24),
            "room_name_edit_cancel": (64, 24),
        }
        assets: dict[str, pygame.Surface] = {}
        for key, path in names.items():
            try:
                assets[key] = pygame.image.load(str(path)).convert_alpha()
            except (FileNotFoundError, pygame.error):
                fallback = pygame.Surface(fallbacks[key], pygame.SRCALPHA)
                fallback.fill((18, 34, 52, 255))
                assets[key] = fallback
        return assets

    def _load_player_preview_frame(self):
        if self._idle_body_frame is not None:
            return
        sprite = self.context.player_animation_path()
        try:
            frames = load_spritesheet_frames(sprite)
        except (FileNotFoundError, pygame.error):
            self._idle_body_frame = None
            return
        self._idle_body_frame = frames["idle_front"][0]

    def _make_avatar_payload(self) -> bytes | None:
        avatar = self.context.current_avatar_source()
        network_avatar = pygame.transform.smoothscale(
            avatar,
            (protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE),
        ).convert_alpha()
        return pygame.image.tobytes(network_avatar, "RGBA")

    def update(self, dt: float, net: nw.Network | None):
        self._send_avatar_if_needed(dt, net)

    def restart_avatar_broadcast(self):
        if self._avatar_payload is None:
            return
        self._avatar_send_timer = 0.0
        self._avatar_send_count = 0

    def _send_avatar_if_needed(self, dt: float, net: nw.Network | None):
        if net is None or self._avatar_payload is None or self._avatar_send_count >= 5:
            return
        self._avatar_send_timer -= dt
        if self._avatar_send_timer > 0:
            return
        net.send_avatar(self._avatar_id, self._avatar_payload, self.context.model_type, self.context.model_color)
        self._avatar_send_count += 1
        self._avatar_send_timer = 1.0

    def handle_avatar_event(self, event, my_id: int) -> bool:
        if isinstance(event, nw.AvatarHeaderEvent):
            self._handle_avatar_header(event, my_id)
            return True
        if isinstance(event, nw.AvatarChunkEvent):
            self._handle_avatar_chunk(event, my_id)
            return True
        return False

    def _handle_avatar_header(self, event: nw.AvatarHeaderEvent, my_id: int):
        if event.player_id == my_id:
            return
        self._remote_models[event.player_id] = (event.model_type, event.model_color)
        key = (event.player_id, event.avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            assembly = AvatarAssembly(total_chunks=event.total_chunks)
            self._avatar_assemblies[key] = assembly
        assembly.total_chunks = event.total_chunks
        assembly.payload_size = event.payload_size
        self._try_complete_avatar(event.player_id, event.avatar_id)

    def _handle_avatar_chunk(self, event: nw.AvatarChunkEvent, my_id: int):
        if event.player_id == my_id:
            return
        key = (event.player_id, event.avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            assembly = AvatarAssembly(total_chunks=event.total_chunks)
            self._avatar_assemblies[key] = assembly
        assembly.total_chunks = event.total_chunks
        assembly.chunks[event.chunk_index] = event.payload
        self._try_complete_avatar(event.player_id, event.avatar_id)

    def _try_complete_avatar(self, player_id: int, avatar_id: int):
        key = (player_id, avatar_id)
        assembly = self._avatar_assemblies.get(key)
        if assembly is None:
            return
        if assembly.payload_size != protocol.NETWORK_AVATAR_BYTES:
            return
        if len(assembly.chunks) < assembly.total_chunks:
            return
        try:
            raw = b"".join(assembly.chunks[index] for index in range(assembly.total_chunks))
        except KeyError:
            return
        raw = raw[: assembly.payload_size]
        if len(raw) != protocol.NETWORK_AVATAR_BYTES:
            return
        try:
            avatar = pygame.image.frombytes(
                raw,
                (protocol.NETWORK_AVATAR_SIZE, protocol.NETWORK_AVATAR_SIZE),
                "RGBA",
            ).convert_alpha()
        except (ValueError, pygame.error):
            return
        self._remote_avatar_surfaces[player_id] = avatar
        for old_key in list(self._avatar_assemblies.keys()):
            if old_key[0] == player_id:
                self._avatar_assemblies.pop(old_key, None)

    def clear_remote_avatar(self, player_id: int):
        self._remote_avatar_surfaces.pop(player_id, None)
        self._remote_models.pop(player_id, None)
        for key in list(self._avatar_assemblies.keys()):
            if key[0] == player_id:
                self._avatar_assemblies.pop(key, None)

    def retain_remote_avatars(self, active_player_ids: set[int]):
        for player_id in list(self._remote_avatar_surfaces.keys()):
            if player_id not in active_player_ids:
                self.clear_remote_avatar(player_id)

    def _draw_asset(self, surface: pygame.Surface, key: str, rect: pygame.Rect):
        asset = self._assets.get(key)
        if asset is None:
            return
        if asset.get_size() == rect.size:
            surface.blit(asset, rect)
        else:
            surface.blit(pygame.transform.scale(asset, rect.size), rect)

    def _draw_window_asset(self, surface: pygame.Surface, key: str, logical_rect: pygame.Rect):
        asset = self._assets.get(key)
        if asset is None:
            return
        rect = self._scale_rect(logical_rect)
        surface.blit(pygame.transform.scale(asset, rect.size), rect)

    def _draw_hover_outline(self, surface: pygame.Surface, rect: pygame.Rect):
        pygame.draw.rect(surface, (115, 190, 255), rect.inflate(2, 2), width=1, border_radius=2)

    def player_card_layout(self, card: pygame.Rect) -> dict[str, pygame.Rect]:
        platform_size = self._assets.get("player_platform", pygame.Surface((30, 17))).get_size()
        status_size = self._assets.get("status_ready", pygame.Surface((36, 14))).get_size()
        name = pygame.Rect(card.centerx - 19, card.y + 6, 38, 12)
        status = pygame.Rect(
            card.centerx - status_size[0] // 2,
            card.bottom - 8 - status_size[1],
            status_size[0],
            status_size[1],
        )
        platform = pygame.Rect(
            card.centerx - platform_size[0] // 2,
            status.y - 4 - platform_size[1],
            platform_size[0],
            platform_size[1],
        )
        model = pygame.Rect(
            card.centerx - PLAYER_FRAME_WIDTH // 2,
            platform.y + 9 - PLAYER_FRAME_HEIGHT,
            PLAYER_FRAME_WIDTH,
            PLAYER_FRAME_HEIGHT,
        )
        return {
            "name": name,
            "model": model,
            "platform": platform,
            "status": status,
            "status_text": pygame.Rect(status.x + 2, status.y + 2, 32, 10),
            "kick_text": pygame.Rect(status.x + 3, status.y + 2, 30, 10),
        }

    def button_layout(self, host_view: bool) -> dict[str, pygame.Rect]:
        if host_view:
            total_w = LOBBY_BUTTON_SIZE[0] * 2 + KICK_MODE_BUTTON_SIZE[0] + BUTTON_GAP * 2
            x = (INTERNAL_WIDTH - total_w) // 2
            primary = pygame.Rect(x, BUTTON_Y, *LOBBY_BUTTON_SIZE)
            secondary = pygame.Rect(primary.right + BUTTON_GAP, BUTTON_Y, *LOBBY_BUTTON_SIZE)
            kick_toggle = pygame.Rect(secondary.right + BUTTON_GAP, BUTTON_Y, *KICK_MODE_BUTTON_SIZE)
            return {
                "primary": primary,
                "secondary": secondary,
                "kick_toggle": kick_toggle,
            }
        total_w = LOBBY_BUTTON_SIZE[0] * 2 + BUTTON_GAP
        x = (INTERNAL_WIDTH - total_w) // 2
        primary = pygame.Rect(x, BUTTON_Y, *LOBBY_BUTTON_SIZE)
        secondary = pygame.Rect(primary.right + BUTTON_GAP, BUTTON_Y, *LOBBY_BUTTON_SIZE)
        return {
            "primary": primary,
            "secondary": secondary,
        }

    def room_title_text_rect(self) -> pygame.Rect:
        frame = ROOM_LOBBY_RECTS["room_name"]
        return pygame.Rect(frame.x + 6, frame.bottom - 13, frame.w - 12, 12)

    def room_title_name_rect(self, room_name: str, host_view: bool) -> pygame.Rect:
        rect = self.room_title_text_rect()
        if not host_view:
            return rect
        scale = self._window_scale()
        font = self._window_font(7)
        prefix_w = int(math.ceil(font.size("Hosting: ")[0] / max(1, scale)))
        max_w = max(0, rect.w - prefix_w)
        return pygame.Rect(rect.x + prefix_w, rect.y, max_w, rect.h)

    def room_name_hit_test(self, pos: tuple[int, int], room_name: str, host_view: bool) -> bool:
        if not host_view:
            return False
        return self.room_title_name_rect(room_name, host_view).collidepoint(pos)

    def player_count_text_rect(self) -> pygame.Rect:
        frame = ROOM_LOBBY_RECTS["player_count"]
        return pygame.Rect(frame.x + 4, frame.bottom - 13, frame.w - 8, 12)

    def starting_window_rect(self) -> pygame.Rect:
        asset = self._assets.get("starting_window")
        frame_w, frame_h = asset.get_size() if asset is not None else (148, 84)
        return pygame.Rect((INTERNAL_WIDTH - frame_w) // 2, (INTERNAL_HEIGHT - frame_h) // 2, frame_w, frame_h)

    def close_confirmation_rect(self) -> pygame.Rect:
        asset = self._assets.get("close_confirmation_window")
        frame_w, frame_h = asset.get_size() if asset is not None else (148, 84)
        return pygame.Rect((INTERNAL_WIDTH - frame_w) // 2, (INTERNAL_HEIGHT - frame_h) // 2, frame_w, frame_h)

    def close_confirmation_layout(self) -> dict[str, pygame.Rect]:
        frame = self.close_confirmation_rect()
        close_asset = self._assets.get("close_confirmation_close")
        cancel_asset = self._assets.get("close_confirmation_cancel")
        close_w, close_h = close_asset.get_size() if close_asset is not None else (64, 24)
        cancel_w, cancel_h = cancel_asset.get_size() if cancel_asset is not None else (64, 24)
        return {
            "frame": frame,
            "message": pygame.Rect(frame.x + 7, frame.y + 7, 134, 40),
            "close": pygame.Rect(frame.x + 7, frame.bottom - 7 - close_h, close_w, close_h),
            "cancel": pygame.Rect(frame.right - 7 - cancel_w, frame.bottom - 7 - cancel_h, cancel_w, cancel_h),
        }

    def room_name_edit_layout(self) -> dict[str, pygame.Rect]:
        frame_asset = self._assets.get("room_name_edit_frame")
        field_asset = self._assets.get("room_name_edit_field")
        button_asset = self._assets.get("room_name_edit_save")
        frame_w, frame_h = frame_asset.get_size() if frame_asset is not None else (148, 84)
        field_w, field_h = field_asset.get_size() if field_asset is not None else (134, 18)
        button_w, button_h = button_asset.get_size() if button_asset is not None else (64, 24)
        frame = pygame.Rect((INTERNAL_WIDTH - frame_w) // 2, (INTERNAL_HEIGHT - frame_h) // 2, frame_w, frame_h)
        title = pygame.Rect(frame.x + 7, frame.y + 7, frame.w - 14, 16)
        field = pygame.Rect(frame.centerx - field_w // 2, title.bottom + 2, field_w, field_h)
        button_y = field.bottom + 8
        button_gap = 8
        total_button_w = button_w * 2 + button_gap
        save = pygame.Rect(frame.centerx - total_button_w // 2, button_y, button_w, button_h)
        cancel = pygame.Rect(save.right + button_gap, button_y, button_w, button_h)
        return {
            "frame": frame,
            "title": title,
            "field": field,
            "text": pygame.Rect(field.x + 5, field.y + 3, 124, 12),
            "count": pygame.Rect(field.x + 7, field.y + 3, field.w - 14, 12),
            "save": save,
            "cancel": cancel,
        }

    def _status_asset_key(self, status: LobbyPlayerStatus) -> str:
        if status is LobbyPlayerStatus.HOST:
            return "status_host"
        if status is LobbyPlayerStatus.READY:
            return "status_ready"
        return "status_waiting"

    def sorted_roster(self, roster: list) -> list:
        return sorted(list(roster), key=lambda row: row[0])[: protocol.MAX_PLAYERS]

    def draw_base(
        self,
        surface: pygame.Surface,
        roster: list,
        host_id: int | None,
        host_view: bool,
        kick_mode: bool,
        hovered,
        primary_enabled: bool = True,
    ):
        self._draw_asset(surface, "background", ROOM_LOBBY_RECTS["background"])
        self._draw_asset(surface, "room_name", ROOM_LOBBY_RECTS["room_name"])
        self._draw_asset(surface, "player_count", ROOM_LOBBY_RECTS["player_count"])
        self._draw_asset(surface, "screen", ROOM_LOBBY_RECTS["screen"])

        entries = self.sorted_roster(roster)
        for index, card in enumerate(PLAYER_CARD_RECTS):
            self._draw_asset(surface, "player_card", card)
            if index >= len(entries):
                continue
            player_id, ready, _name = entries[index]
            is_host = host_id is not None and player_id == host_id
            layout = self.player_card_layout(card)
            self._draw_asset(surface, "player_platform", layout["platform"])
            if self._idle_body_frame is None:
                self._draw_asset(surface, "player_model", pygame.Rect(layout["model"].x + 1, layout["model"].y, 22, 32))
            status = lobby_player_status(is_host, ready)
            if host_view and kick_mode and not is_host:
                self._draw_asset(surface, "kick_player", layout["status"])
                if hovered == ("kick", player_id):
                    self._draw_hover_outline(surface, layout["status"])
            else:
                self._draw_asset(surface, self._status_asset_key(status), layout["status"])

        buttons = self.button_layout(host_view)
        primary_asset = "ready_start" if primary_enabled else "ready_start_disabled"
        self._draw_asset(surface, primary_asset, buttons["primary"])
        if host_view:
            self._draw_asset(surface, "host_close", buttons["secondary"])
            mode_key = "kick_mode_on" if kick_mode else "kick_mode_off"
            icon_key = "kick_mode_on_icon" if kick_mode else "kick_mode_off_icon"
            self._draw_asset(surface, mode_key, buttons["kick_toggle"])
            icon = self._assets.get(icon_key)
            if icon is not None:
                icon_rect = icon.get_rect(center=buttons["kick_toggle"].center)
                surface.blit(icon, icon_rect)
        else:
            self._draw_asset(surface, "leave", buttons["secondary"])

        if hovered == "primary" and primary_enabled:
            self._draw_hover_outline(surface, buttons["primary"])
        if hovered == "secondary":
            self._draw_hover_outline(surface, buttons["secondary"])
        if host_view and hovered == "kick_toggle":
            self._draw_hover_outline(surface, buttons["kick_toggle"])

    def hit_test(
        self,
        pos: tuple[int, int],
        roster: list,
        host_id: int | None,
        host_view: bool,
        kick_mode: bool,
    ):
        buttons = self.button_layout(host_view)
        if buttons["primary"].collidepoint(pos):
            return "primary"
        if buttons["secondary"].collidepoint(pos):
            return "secondary"
        if host_view and buttons["kick_toggle"].collidepoint(pos):
            return "kick_toggle"
        if host_view and kick_mode:
            for index, entry in enumerate(self.sorted_roster(roster)):
                if index >= len(PLAYER_CARD_RECTS):
                    break
                player_id, _ready, name = entry
                if host_id is not None and player_id == host_id:
                    continue
                layout = self.player_card_layout(PLAYER_CARD_RECTS[index])
                if layout["status"].collidepoint(pos):
                    return ("kick", player_id, name)
        return None

    def close_confirmation_hit_test(self, pos: tuple[int, int]):
        layout = self.close_confirmation_layout()
        if layout["close"].collidepoint(pos):
            return "close"
        if layout["cancel"].collidepoint(pos):
            return "cancel"
        return None

    def room_name_edit_hit_test(self, pos: tuple[int, int]):
        layout = self.room_name_edit_layout()
        if layout["save"].collidepoint(pos):
            return "save"
        if layout["cancel"].collidepoint(pos):
            return "cancel"
        if layout["field"].collidepoint(pos):
            return "field"
        if layout["frame"].collidepoint(pos):
            return "frame"
        return None

    def draw_close_confirmation_base(self, surface: pygame.Surface, hovered=None):
        self._draw_dim_scrim(surface, None)
        layout = self.close_confirmation_layout()
        self._draw_asset(surface, "close_confirmation_window", layout["frame"])
        self._draw_asset(surface, "close_confirmation_close", layout["close"])
        self._draw_asset(surface, "close_confirmation_cancel", layout["cancel"])
        if hovered == "close":
            self._draw_hover_outline(surface, layout["close"])
        elif hovered == "cancel":
            self._draw_hover_outline(surface, layout["cancel"])

    def draw_room_name_edit_base(self, surface: pygame.Surface, save_enabled: bool, field_active: bool, hovered=None):
        self._draw_dim_scrim(surface, None)
        layout = self.room_name_edit_layout()
        self._draw_asset(surface, "room_name_edit_frame", layout["frame"])
        self._draw_asset(surface, "room_name_edit_field", layout["field"])
        save_key = "room_name_edit_save" if save_enabled else "room_name_edit_save_disabled"
        self._draw_asset(surface, save_key, layout["save"])
        self._draw_asset(surface, "room_name_edit_cancel", layout["cancel"])
        if field_active:
            self._draw_hover_outline(surface, layout["field"])
        if save_enabled and hovered == "save":
            self._draw_hover_outline(surface, layout["save"])
        if hovered == "cancel":
            self._draw_hover_outline(surface, layout["cancel"])

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

    def _fit_text(self, text: str, font: pygame.font.Font, max_width: int) -> str:
        if font.size(text)[0] <= max_width:
            return text
        out = text
        while out and font.size(out + ".")[0] > max_width:
            out = out[:-1]
        return (out + ".") if out else "."

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
        text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        if shadow:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, shade.get_rect(center=(rect.centerx + scale, rect.centery + scale)))
        label = font.render(text, True, color)
        surface.blit(label, label.get_rect(center=rect.center))

    def _draw_text_left(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        bold: bool = True,
        shadow: bool = False,
    ):
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size, bold=bold)
        text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        y = rect.y + (rect.h - font.get_height()) // 2
        if shadow:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, (rect.x + scale, y + scale))
        label = font.render(text, True, color)
        surface.blit(label, (rect.x, y))

    def _draw_text_right_alpha(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        alpha: int,
    ):
        rect = self._scale_rect(logical_rect)
        font = self._window_font(logical_size, bold=True)
        label = font.render(text, True, color)
        label.set_alpha(alpha)
        y = rect.y + (rect.h - font.get_height()) // 2
        surface.blit(label, (rect.right - label.get_width(), y))

    def _draw_text_caret(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
    ):
        if int(pygame.time.get_ticks() / 500) % 2 != 0:
            return
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size, bold=True)
        fitted_text = self._fit_text(text, font, max(4, rect.w - (4 * scale)))
        text_width = font.size(fitted_text)[0] if fitted_text else 0
        caret_w = max(1, scale)
        caret_h = max(caret_w, font.get_height() - (2 * scale))
        x = min(rect.right - caret_w, rect.x + text_width + scale)
        y = rect.y + (rect.h - caret_h) // 2
        pygame.draw.rect(surface, color, pygame.Rect(x, y, caret_w, caret_h))

    def _draw_marquee_text(
        self,
        surface: pygame.Surface,
        logical_size: int,
        text: str,
        logical_rect: pygame.Rect,
        color: tuple[int, int, int],
        seed: int,
    ):
        rect = self._scale_rect(logical_rect)
        scale = self._window_scale()
        font = self._window_font(logical_size, bold=True)
        label = font.render(text, True, color)
        if label.get_width() <= rect.w:
            shade = font.render(text, True, (8, 14, 25))
            surface.blit(shade, shade.get_rect(center=(rect.centerx + scale, rect.centery + scale)))
            surface.blit(label, label.get_rect(center=rect.center))
            return

        period = 4.2
        phase = ((time.monotonic() + seed * 0.23) % period) / period
        sweep = phase * 2.0 if phase < 0.5 else (1.0 - phase) * 2.0
        offset = int((label.get_width() - rect.w) * sweep)
        y = rect.y + (rect.h - font.get_height()) // 2
        previous_clip = surface.get_clip()
        surface.set_clip(rect)
        shade = font.render(text, True, (8, 14, 25))
        surface.blit(shade, (rect.x - offset + scale, y + scale))
        surface.blit(label, (rect.x - offset, y))
        surface.set_clip(previous_clip)

    def _current_avatar_source(self) -> pygame.Surface:
        return self.context.current_avatar_source()

    def _avatar_for_player(self, player_id: int, local_player_id: int | None) -> pygame.Surface:
        if local_player_id is not None and player_id == local_player_id:
            return self._current_avatar_source()
        return self._remote_avatar_surfaces.get(player_id) or make_default_avatar(self.context.project_root)

    def _body_frame_for_player(self, player_id: int, local_player_id: int | None) -> pygame.Surface | None:
        if local_player_id is not None and player_id == local_player_id:
            return self._idle_body_frame
        model_type, model_color = self._remote_models.get(
            player_id,
            (protocol.DEFAULT_MODEL_TYPE, protocol.DEFAULT_MODEL_COLOR),
        )
        key = (model_type, model_color)
        if key not in self._body_frame_cache:
            try:
                frames = load_spritesheet_frames(animation_path(self.context.project_root, model_type, model_color))
                self._body_frame_cache[key] = frames["idle_front"][0]
            except (FileNotFoundError, pygame.error):
                return self._idle_body_frame
        return self._body_frame_cache.get(key)

    def _draw_player_model(
        self,
        surface: pygame.Surface,
        logical_rect: pygame.Rect,
        avatar: pygame.Surface,
        body_frame: pygame.Surface | None,
    ):
        if body_frame is None:
            return
        frame_rect = self._scale_rect(logical_rect)
        avatar_logical = pygame.Rect(
            logical_rect.x + AVATAR_RECT.x,
            logical_rect.y + AVATAR_RECT.y,
            AVATAR_RECT.w,
            AVATAR_RECT.h,
        )
        avatar_rect = self._scale_rect(avatar_logical)
        avatar_image = pygame.transform.smoothscale(crop_square(avatar), avatar_rect.size)
        body = pygame.transform.scale(body_frame, frame_rect.size)
        surface.blit(avatar_image, avatar_rect)
        surface.blit(body, frame_rect)

    def _status_color(self, status: LobbyPlayerStatus) -> tuple[int, int, int]:
        if status is LobbyPlayerStatus.HOST:
            return (255, 236, 170)
        if status is LobbyPlayerStatus.READY:
            return (130, 235, 145)
        return (245, 245, 250)

    def draw_window_overlay(
        self,
        surface: pygame.Surface,
        roster: list,
        room_name: str,
        host_id: int | None,
        local_player_id: int | None,
        host_view: bool,
        kick_mode: bool,
        primary_enabled: bool,
        primary_label: str,
        secondary_label: str,
        countdown_remaining: float | None = None,
        pulse_t: float = 0.0,
        room_name_hovered: bool = False,
    ):
        theme = DEFAULT_THEME
        buttons = self.button_layout(host_view)
        if countdown_remaining is not None:
            exempt_rect = buttons["primary"].inflate(2, 2) if host_view else None
            self._draw_countdown_focus(surface, countdown_remaining, pulse_t, exempt_rect)
            if host_view:
                primary_color = theme.text if primary_enabled else theme.text_muted
                self._draw_text_center(surface, 7, primary_label, buttons["primary"].inflate(-10, -6), primary_color)
            self.draw_window_global_messages(surface)
            return

        if host_view:
            title_rect = self.room_title_text_rect()
            prefix = "Hosting: "
            self._draw_text_left(surface, 7, prefix, title_rect, theme.text_muted, shadow=True)
            name_rect = self.room_title_name_rect(room_name, host_view)
            name_color = (255, 236, 170) if room_name_hovered else theme.text
            self._draw_text_left(surface, 7, room_name, name_rect, name_color, shadow=True)
        else:
            self._draw_text_left(surface, 7, room_name, self.room_title_text_rect(), theme.text, shadow=True)
        self._draw_text_center(
            surface,
            7,
            f"{len(roster)}/{protocol.MAX_PLAYERS}",
            self.player_count_text_rect(),
            theme.text,
        )

        entries = self.sorted_roster(roster)
        for index, card in enumerate(PLAYER_CARD_RECTS):
            layout = self.player_card_layout(card)
            if index >= len(entries):
                self._draw_text_center(surface, 6, "OPEN", pygame.Rect(card.x + 6, card.y + 31, 38, 10), theme.text_muted)
                self._draw_text_center(surface, 6, "SLOT", pygame.Rect(card.x + 6, card.y + 43, 38, 10), theme.text_muted)
                continue

            player_id, ready, name = entries[index]
            is_host = host_id is not None and player_id == host_id
            status = lobby_player_status(is_host, ready)
            self._draw_marquee_text(surface, 6, name, layout["name"], (215, 235, 250), player_id)
            self._draw_player_model(
                surface,
                layout["model"],
                self._avatar_for_player(player_id, local_player_id),
                self._body_frame_for_player(player_id, local_player_id),
            )
            if host_view and kick_mode and not is_host:
                self._draw_text_center(surface, 5, "KICK", layout["kick_text"], theme.text, shadow=True)
            else:
                self._draw_text_center(surface, 5, status.value, layout["status_text"], self._status_color(status), shadow=True)

        primary_color = theme.text if primary_enabled else theme.text_muted
        self._draw_text_center(surface, 7, primary_label, buttons["primary"].inflate(-10, -6), primary_color)
        self._draw_text_center(surface, 7, secondary_label, buttons["secondary"].inflate(-10, -6), theme.text)

        self.draw_window_global_messages(surface)

    def draw_close_confirmation_window_overlay(self, surface: pygame.Surface):
        theme = DEFAULT_THEME
        layout = self.close_confirmation_layout()
        message = layout["message"]
        self._draw_text_center(
            surface,
            9,
            "Close Room?",
            pygame.Rect(message.x, message.y + 4, message.w, 14),
            theme.text,
        )
        self._draw_text_center(
            surface,
            5,
            "All players will be kicked out",
            pygame.Rect(message.x, message.y + 21, message.w, 11),
            theme.text_muted,
        )
        self._draw_text_center(surface, 7, "CLOSE", layout["close"].inflate(-8, -6), theme.text)
        self._draw_text_center(surface, 7, "CANCEL", layout["cancel"].inflate(-8, -6), theme.text)
        self.draw_window_global_messages(surface)

    def draw_room_name_edit_window_overlay(
        self,
        surface: pygame.Surface,
        value: str,
        save_enabled: bool,
        field_active: bool,
    ):
        theme = DEFAULT_THEME
        layout = self.room_name_edit_layout()
        self._draw_text_center(surface, 7, "Edit Room Name", layout["title"], (180, 220, 255))
        self._draw_text_left(surface, 7, value, layout["text"], theme.text, shadow=False)
        self._draw_text_right_alpha(
            surface,
            7,
            f"{len(value)}/{protocol.ROOM_NAME_MAX_LEN}",
            layout["count"],
            theme.text_muted,
            191,
        )
        if field_active:
            self._draw_text_caret(surface, 7, value, layout["text"], theme.text)
        save_color = theme.text if save_enabled else theme.text_muted
        self._draw_text_center(surface, 7, "SAVE", layout["save"], save_color)
        self._draw_text_center(surface, 7, "CANCEL", layout["cancel"], theme.text)
        self.draw_window_global_messages(surface)

    def _draw_dim_scrim(self, surface: pygame.Surface, exempt_logical_rect: pygame.Rect | None):
        scrim = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        color = (0, 0, 0, 145)
        if exempt_logical_rect is None:
            scrim.fill(color)
            surface.blit(scrim, (0, 0))
            return

        exempt = self._scale_rect(exempt_logical_rect).clip(surface.get_rect())
        if exempt.w <= 0 or exempt.h <= 0:
            scrim.fill(color)
            surface.blit(scrim, (0, 0))
            return

        w, h = surface.get_size()
        for rect in (
            pygame.Rect(0, 0, w, exempt.top),
            pygame.Rect(0, exempt.bottom, w, h - exempt.bottom),
            pygame.Rect(0, exempt.top, exempt.left, exempt.h),
            pygame.Rect(exempt.right, exempt.top, w - exempt.right, exempt.h),
        ):
            if rect.w > 0 and rect.h > 0:
                pygame.draw.rect(scrim, color, rect)
        surface.blit(scrim, (0, 0))

    def _draw_countdown_focus(
        self,
        surface: pygame.Surface,
        countdown_remaining: float,
        pulse_t: float,
        exempt_logical_rect: pygame.Rect | None,
    ):
        theme = DEFAULT_THEME
        self._draw_dim_scrim(surface, exempt_logical_rect)
        frame = self.starting_window_rect()
        self._draw_window_asset(surface, "starting_window", frame)

        seconds = max(0, int(countdown_remaining + 0.999))
        scale_factor = 0.92 + 0.08 * (0.5 + 0.5 * math.sin(pulse_t * 8.0))
        font = self._window_font(24, bold=True)
        label = font.render(str(seconds), True, theme.badge_starting)
        label = pygame.transform.smoothscale(
            label,
            (
                max(1, int(label.get_width() * scale_factor)),
                max(1, int(label.get_height() * scale_factor)),
            ),
        )
        center = self._scale_rect(pygame.Rect(frame.x, frame.y + 23, frame.w, 34)).center
        surface.blit(label, label.get_rect(center=center))
        self._draw_text_center(
            surface,
            7,
            "GET READY",
            pygame.Rect(frame.x + 18, frame.y + 56, frame.w - 36, 14),
            theme.text_muted,
        )

    def draw_window_global_messages(self, surface: pygame.Surface):
        scale = self._window_scale()
        if self.context.banner_message:
            rect = pygame.Rect(0, 0, surface.get_width(), 30 * scale)
            pygame.draw.rect(surface, (120, 40, 50), rect)
            font = self._window_font(7)
            label = font.render(self.context.banner_message, True, DEFAULT_THEME.text)
            surface.blit(label, (10 * scale, 5 * scale))
        if self.context.status_message:
            y = 34 * scale if self.context.banner_message else 8 * scale
            font = self._window_font(6)
            label = font.render(self.context.status_message, True, (255, 230, 120))
            surface.blit(label, (8 * scale, y))
