import logging
from datetime import datetime
from pathlib import Path


def safe_log_name(value: str, fallback: str = "instance") -> str:
    safe = "".join(ch for ch in value.strip() if ch.isalnum() or ch in ("-", "_"))
    return safe or fallback


def create_instance_log_dir(project_root: Path, player_name: str) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    folder_name = f"{stamp}-{safe_log_name(player_name, 'player')}"
    log_dir = project_root / "logs" / folder_name
    suffix = 2
    while log_dir.exists():
        log_dir = project_root / "logs" / f"{folder_name}-{suffix}"
        suffix += 1
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def configure_logging(log_level: str, log_file: Path | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
