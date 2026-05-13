import pygame

from ui.results_table import draw_results_table


def test_results_table_draws_extended_standings_header_without_crashing():
    pygame.font.init()
    surface = pygame.Surface((640, 360))
    fonts = (
        pygame.font.Font(None, 28),
        pygame.font.Font(None, 20),
        pygame.font.Font(None, 16),
    )

    draw_results_table(
        surface,
        fonts,
        standings=[(1, 1, "KURT", 12345, 42)],
        elapsed=1.0,
        placement_label_fn=lambda placement: str(placement),
    )
