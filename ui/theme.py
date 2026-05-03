from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Palette and typography defaults for lobby polish."""

    # Backgrounds
    bg: tuple[int, int, int] = (18, 20, 28)
    bg_panel: tuple[int, int, int] = (32, 36, 52)
    bg_input: tuple[int, int, int] = (40, 44, 60)

    # Content
    text: tuple[int, int, int] = (245, 247, 252)
    text_muted: tuple[int, int, int] = (160, 168, 188)
    text_warn: tuple[int, int, int] = (255, 190, 100)
    border: tuple[int, int, int] = (90, 98, 120)
    border_focus: tuple[int, int, int] = (130, 180, 255)

    # Actions
    accent: tuple[int, int, int] = (70, 130, 220)
    accent_hover: tuple[int, int, int] = (95, 155, 245)
    accent_disabled: tuple[int, int, int] = (55, 58, 70)
    danger: tuple[int, int, int] = (180, 60, 70)
    danger_hover: tuple[int, int, int] = (210, 80, 90)

    # Room badges (plan: LOBBY green / STARTING & FULL amber / IN GAME red)
    badge_lobby: tuple[int, int, int] = (50, 160, 90)
    badge_starting: tuple[int, int, int] = (215, 165, 55)
    badge_full: tuple[int, int, int] = (210, 155, 65)
    badge_ingame: tuple[int, int, int] = (200, 55, 55)

    card_joinable: tuple[int, int, int] = (38, 52, 72)
    card_dim: tuple[int, int, int] = (28, 30, 38)

    overlay_scrim: tuple[int, int, int, int] = (8, 10, 18, 220)

    # Fonts (logical names; pygame SysFont)
    font_title: str = "segoe ui"
    font_body: str = "segoe ui"
    size_title: int = 32
    size_large: int = 24
    size_small: int = 18
    size_tiny: int = 15


DEFAULT_THEME = Theme()
