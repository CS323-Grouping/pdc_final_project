from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
import json
import os
from pathlib import Path
import tempfile

from network import protocol


SCHEMA_VERSION = 1
APP_FOLDER_NAME = "Skyward Race"
DEV_PROFILE_COUNT = 5
PROFILE_FILENAME = "profile.json"
LOCK_FILENAME = "session.lock"
CUSTOM_HEAD_FILENAME = "head.png"


@dataclass
class ProfileData:
    player_name: str
    model_type: str = protocol.DEFAULT_MODEL_TYPE
    model_color: str = protocol.DEFAULT_MODEL_COLOR
    use_custom_head: bool = False
    head_texture: str = CUSTOM_HEAD_FILENAME
    schema_version: int = SCHEMA_VERSION
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ProfileSession:
    slot_name: str
    profile_dir: Path
    data: ProfileData
    lock_path: Path | None = None

    @property
    def profile_path(self) -> Path:
        return self.profile_dir / PROFILE_FILENAME

    @property
    def custom_head_path(self) -> Path:
        return self.profile_dir / self.data.head_texture

    def save(self) -> None:
        save_profile(self)

    def release(self) -> None:
        if self.lock_path is None:
            return
        try:
            current = _read_lock_pid(self.lock_path)
            if current == os.getpid():
                self.lock_path.unlink(missing_ok=True)
        finally:
            self.lock_path = None


def documents_user_data_root() -> Path:
    home = Path.home()
    documents = home / "Documents"
    if not documents.exists():
        documents = home
    return documents / APP_FOLDER_NAME / "user_data"


def profiles_root() -> Path:
    return documents_user_data_root() / "profiles"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _profile_from_dict(raw: dict, fallback_name: str) -> ProfileData:
    created_at = str(raw.get("created_at") or _now_iso())
    player_name = str(raw.get("player_name") or fallback_name)
    if not protocol.is_valid_player_name(player_name):
        player_name = fallback_name
    model_type = protocol.normalize_model_type(str(raw.get("model_type") or protocol.DEFAULT_MODEL_TYPE))
    model_color = protocol.normalize_model_color(str(raw.get("model_color") or protocol.DEFAULT_MODEL_COLOR))
    return ProfileData(
        schema_version=SCHEMA_VERSION,
        player_name=player_name,
        model_type=model_type,
        model_color=model_color,
        use_custom_head=bool(raw.get("use_custom_head", False)),
        head_texture=str(raw.get("head_texture") or CUSTOM_HEAD_FILENAME),
        created_at=created_at,
        updated_at=str(raw.get("updated_at") or created_at),
    )


def _default_profile(fallback_name: str) -> ProfileData:
    now = _now_iso()
    return ProfileData(
        player_name=fallback_name,
        created_at=now,
        updated_at=now,
    )


def _load_profile_data(profile_dir: Path, fallback_name: str) -> ProfileData:
    profile_path = profile_dir / PROFILE_FILENAME
    if not profile_path.exists():
        return _default_profile(fallback_name)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_profile(fallback_name)
    if not isinstance(raw, dict):
        return _default_profile(fallback_name)
    return _profile_from_dict(raw, fallback_name)


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.write("\n")
        temp_path = Path(tmp.name)
    temp_path.replace(path)


def save_profile(session: ProfileSession) -> None:
    session.profile_dir.mkdir(parents=True, exist_ok=True)
    session.data.model_type = protocol.normalize_model_type(session.data.model_type)
    session.data.model_color = protocol.normalize_model_color(session.data.model_color)
    session.data.updated_at = _now_iso()
    if not session.data.created_at:
        session.data.created_at = session.data.updated_at
    payload = {
        "schema_version": SCHEMA_VERSION,
        "player_name": session.data.player_name,
        "model_type": session.data.model_type,
        "model_color": session.data.model_color,
        "use_custom_head": session.data.use_custom_head,
        "head_texture": session.data.head_texture,
        "created_at": session.data.created_at,
        "updated_at": session.data.updated_at,
    }
    _write_json_atomic(session.profile_path, payload)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_lock_pid(lock_path: Path) -> int | None:
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return int(raw.get("pid"))
    except (AttributeError, TypeError, ValueError):
        return None


def _try_claim_slot(profile_dir: Path) -> Path | None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    lock_path = profile_dir / LOCK_FILENAME
    pid = _read_lock_pid(lock_path)
    if pid is not None and not _pid_alive(pid):
        lock_path.unlink(missing_ok=True)

    payload = json.dumps({"pid": os.getpid(), "created_at": _now_iso()})
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return lock_path


def _load_session(slot_name: str, fallback_name: str, lock_path: Path | None = None) -> ProfileSession:
    profile_dir = profiles_root() / slot_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    data = _load_profile_data(profile_dir, fallback_name)
    session = ProfileSession(slot_name=slot_name, profile_dir=profile_dir, data=data, lock_path=lock_path)
    save_profile(session)
    return session


def load_profile_session(dev_mode: bool, fallback_name: str) -> ProfileSession:
    root = profiles_root()
    root.mkdir(parents=True, exist_ok=True)
    if not dev_mode:
        return _load_session("default", fallback_name)

    for index in range(1, DEV_PROFILE_COUNT + 1):
        slot_name = f"DevProfile{index}"
        profile_dir = root / slot_name
        lock_path = _try_claim_slot(profile_dir)
        if lock_path is not None:
            return _load_session(slot_name, fallback_name, lock_path=lock_path)
    raise RuntimeError("All development profiles are currently in use. Close another game instance first.")
