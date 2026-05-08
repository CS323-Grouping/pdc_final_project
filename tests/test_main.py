from pathlib import Path
from types import SimpleNamespace

import pytest

import main as main_module


class DummyContext:
    def __init__(self, project_root: Path):
        self.player_name = "ValidName"
        self.project_root = project_root
        self.log_dir = None
        self.save_profile_calls = 0

    def apply_profile_session(self, _session):
        return None

    def save_profile(self):
        self.save_profile_calls += 1


def test_invalid_cli_name_does_not_save_profile(monkeypatch, tmp_path):
    args = SimpleNamespace(
        log_level="INFO",
        dev=False,
        name="bad name",
        host=False,
        room="GameRoom",
        server="",
    )
    created: dict[str, DummyContext] = {}

    def fake_context(**_kwargs):
        ctx = DummyContext(tmp_path)
        created["ctx"] = ctx
        return ctx

    monkeypatch.setattr(main_module, "parse_args", lambda: args)
    monkeypatch.setattr(main_module.pygame, "init", lambda: None)
    monkeypatch.setattr(main_module.pygame.key, "set_repeat", lambda *_args: None)
    monkeypatch.setattr(main_module.pygame.time, "Clock", lambda: object())
    monkeypatch.setattr(main_module.pygame, "quit", lambda: None)
    monkeypatch.setattr(main_module.DisplayManager, "create_default", lambda: SimpleNamespace(screen=None))
    monkeypatch.setattr(main_module, "AppContext", fake_context)
    monkeypatch.setattr(main_module, "load_profile_session", lambda _dev, _name: object())
    monkeypatch.setattr(main_module, "create_instance_log_dir", lambda _root, _name: tmp_path)
    monkeypatch.setattr(main_module, "configure_logging", lambda *_args, **_kwargs: None)

    with pytest.raises(SystemExit) as error:
        main_module.main()

    assert error.value.code == 1
    assert created["ctx"].save_profile_calls == 0
