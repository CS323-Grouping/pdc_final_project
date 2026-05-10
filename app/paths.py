"""Resolve bundle vs dev filesystem paths (PyInstaller, etc.)."""

from __future__ import annotations

import sys
from pathlib import Path

_DEV_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    """True when running as a packaged app (PyInstaller, cx_Freeze, etc.)."""
    return bool(getattr(sys, "frozen", False))


def _frozen_resource_candidates() -> list[Path]:
    """Ordered search paths for bundled read-only content (assets, etc.)."""
    exe_dir = Path(sys.executable).resolve().parent
    out: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        try:
            r = p.resolve()
        except OSError:
            return
        if r not in seen:
            seen.add(r)
            out.append(r)

    if hasattr(sys, "_MEIPASS"):
        add(Path(sys._MEIPASS))
    # PyInstaller 6+ onedir: payload often lives beside the exe in _internal/
    add(exe_dir / "_internal")
    add(exe_dir)

    return out


def _fatal_missing_game_data(checked: list[Path]) -> None:
    places = "\n".join(f"  - {p}" for p in checked[:6])
    if len(checked) > 6:
        places += "\n  - …"
    msg = (
        "Could not find bundled game data (assets folder).\n\n"
        "Copy the entire build output folder (everything inside dist\\TowerJumpLAN\\), "
        "not only TowerJumpLAN.exe.\n\n"
        f"Searched under:\n{places}"
    )
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, msg, "Tower Jump LAN", 0x10)
        except Exception:
            print(msg, file=sys.stderr)
    else:
        print(msg, file=sys.stderr)
    raise SystemExit(1)


def get_resource_root() -> Path:
    """Read-only bundled content: ``assets/``, data files, and Python modules.

    When frozen, we probe several layouts because PyInstaller version and
    ``onedir`` vs ``onefile`` place ``assets`` under ``sys._MEIPASS``,
    ``<exe_dir>/_internal/``, or next to the executable.
    """

    if not is_frozen():
        return _DEV_PROJECT_ROOT

    tried: list[Path] = []
    for base in _frozen_resource_candidates():
        tried.append(base)
        if (base / "assets").is_dir():
            return base

    _fatal_missing_game_data(tried)


def get_writable_root() -> Path:
    """Logs and other files safe to create at runtime (beside the exe when bundled)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return _DEV_PROJECT_ROOT
