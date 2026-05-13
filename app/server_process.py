"""Manages the local server subprocess used when hosting a LAN room.

Handles port selection, process spawn (script vs frozen embedded server),
graceful shutdown, and exit-wait. Owned by ``AppContext.server`` and exposed
through thin delegating methods on AppContext for backward compatibility.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)

GAME_PORT_SEARCH_LIMIT = 50


class LocalServerLauncher:
    def __init__(
        self,
        project_root: Path,
        log_level: str,
        log_dir_provider: Callable[[], Optional[Path]],
        server_host: str = "127.0.0.1",
        server_port: int = 5555,
        discovery_port: int = 5556,
    ):
        self._project_root = project_root
        self._log_level = log_level
        self._log_dir_provider = log_dir_provider
        self.server_host = server_host
        self.server_port = server_port
        self.discovery_port = discovery_port
        self._process: Optional[subprocess.Popen] = None

    @property
    def process(self) -> Optional[subprocess.Popen]:
        return self._process

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, room_name: str) -> bool:
        self.stop()
        self.server_port = self._choose_server_port()
        if getattr(sys, "frozen", False):
            launch_prefix = [sys.executable, "--run-embedded-server"]
        else:
            launch_prefix = [sys.executable, str(self._project_root / "network" / "server.py")]
        command = launch_prefix + [
            "--host", "0.0.0.0",
            "--port", str(self.server_port),
            "--discovery-port", str(self.discovery_port),
            "--room", room_name,
            "--log-level", self._log_level,
            "--owner-pid", str(os.getpid()),
        ]
        log_dir = self._log_dir_provider()
        if log_dir is not None:
            command.extend(["--log-dir", str(log_dir)])
        LOGGER.info("Starting local server room=%s command=%s", room_name, command)
        self._process = subprocess.Popen(command, cwd=str(self._project_root))
        time.sleep(0.4)
        if self._process.poll() is not None:
            LOGGER.error("Local server exited during startup room=%s", room_name)
            self._process = None
            return False
        LOGGER.info("Local server started room=%s port=%s", room_name, self.server_port)
        return True

    def stop(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            LOGGER.info("Stopping local server")
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                LOGGER.warning("Local server did not stop in time; killing")
                self._process.kill()
        self._process = None

    def wait_for_exit(self, timeout: float = 0.75) -> bool:
        if self._process is None:
            return True
        if self._process.poll() is not None:
            self._process = None
            return True
        try:
            self._process.wait(timeout=timeout)
            self._process = None
            LOGGER.info("Local server exited after close-room request")
            return True
        except subprocess.TimeoutExpired:
            LOGGER.warning("Local server did not exit after close-room request")
            return False

    def _udp_port_available(self, port: int) -> bool:
        probe = None
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
        finally:
            if probe is not None:
                probe.close()
        return True

    def _choose_server_port(self) -> int:
        preferred = max(1, min(65535, int(self.server_port)))
        for offset in range(GAME_PORT_SEARCH_LIMIT):
            port = preferred + offset
            if port > 65535:
                break
            if port == self.discovery_port:
                continue
            if self._udp_port_available(port):
                return port

        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.bind(("0.0.0.0", 0))
            return int(probe.getsockname()[1])
        finally:
            probe.close()
