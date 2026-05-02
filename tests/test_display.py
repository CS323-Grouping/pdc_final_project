import pytest

from app.display import DisplayConfig, choose_default_scale


def test_display_config_window_size_uses_integer_scale():
    config = DisplayConfig(selected_scale=4)

    assert config.internal_size == (320, 180)
    assert config.window_size == (1280, 720)


def test_display_config_rejects_unsupported_scale():
    with pytest.raises(ValueError):
        DisplayConfig(selected_scale=7)


def test_choose_default_scale_prefers_comfortable_windowed_size():
    assert choose_default_scale((1920, 1080)) == 4
    assert choose_default_scale((1280, 720)) == 3
    assert choose_default_scale((1366, 768)) == 4
    assert choose_default_scale((640, 360)) == 2
    assert choose_default_scale((320, 180)) == 2
