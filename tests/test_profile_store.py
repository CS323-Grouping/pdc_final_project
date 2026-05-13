import json

from app.profile_store import ProfileData, ProfileSession, _load_profile_data, save_profile


def test_profile_persists_performance_metrics_toggle(tmp_path):
    session = ProfileSession(
        slot_name="test",
        profile_dir=tmp_path,
        data=ProfileData(player_name="PlayerOne", show_performance_metrics=False),
    )

    save_profile(session)
    raw = json.loads(session.profile_path.read_text(encoding="utf-8"))
    loaded = _load_profile_data(tmp_path, "Fallback1")

    assert raw["show_performance_metrics"] is False
    assert loaded.show_performance_metrics is False


def test_profile_defaults_performance_metrics_to_visible(tmp_path):
    (tmp_path / "profile.json").write_text(
        json.dumps({"player_name": "PlayerOne"}),
        encoding="utf-8",
    )

    loaded = _load_profile_data(tmp_path, "Fallback1")

    assert loaded.show_performance_metrics is True


def test_profile_defaults_control_scheme_to_wasd(tmp_path):
    (tmp_path / "profile.json").write_text(
        json.dumps({"player_name": "PlayerOne"}),
        encoding="utf-8",
    )

    loaded = _load_profile_data(tmp_path, "Fallback1")

    assert loaded.control_scheme == "wasd"


def test_profile_persists_control_scheme(tmp_path):
    session = ProfileSession(
        slot_name="test",
        profile_dir=tmp_path,
        data=ProfileData(player_name="PlayerOne", control_scheme="arrows"),
    )

    save_profile(session)
    raw = json.loads(session.profile_path.read_text(encoding="utf-8"))
    loaded = _load_profile_data(tmp_path, "Fallback1")

    assert raw["control_scheme"] == "arrows"
    assert loaded.control_scheme == "arrows"
