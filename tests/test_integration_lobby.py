"""
Subprocess smoke tests (LAN server on loopback).

Run with: pytest tests/test_integration_lobby.py -m integration
Skip in quick runs: pytest -m "not integration"
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from network import protocol

ROOT = Path(__file__).resolve().parents[1]


def _pick_ports(base: int) -> tuple[int, int]:
    """Shift ports if already bound (best-effort)."""
    for delta in range(0, 80, 2):
        g, d = base + delta, base + delta + 1
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("127.0.0.1", g))
        except OSError:
            continue
        finally:
            s.close()
        s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s2.bind(("127.0.0.1", d))
        except OSError:
            continue
        finally:
            s2.close()
        return g, d
    pytest.skip("Could not bind two UDP ports for integration test")


@pytest.mark.integration
def test_sixth_player_gets_room_full():
    game_port, disc_port = _pick_ports(59400)
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "network" / "server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(game_port),
            "--discovery-port",
            str(disc_port),
            "--room",
            "FullCap",
            "--log-level",
            "ERROR",
        ],
        cwd=str(ROOT),
    )
    time.sleep(0.55)
    clients = []
    try:
        if proc.poll() is not None:
            pytest.fail("Server process exited early — port conflict or bad args")

        from tools.scripted_lobby import FakeClient

        for i in range(5):
            c = FakeClient(f"Cap{i}", "127.0.0.1", game_port)
            ok, reason, _extra = c.connect()
            assert ok, f"player {i} join failed"
            clients.append(c)

        late = FakeClient("TooMany", "127.0.0.1", game_port)
        ok, reason, _extra = late.connect()
        assert not ok
        assert reason == protocol.CONNO_REASON_FULL
        late.close()
    finally:
        for c in clients:
            c.close()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.integration
def test_malformed_datagram_does_not_break_server():
    game_port, disc_port = _pick_ports(59520)
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "network" / "server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(game_port),
            "--discovery-port",
            str(disc_port),
            "--room",
            "NoiseRoom",
            "--log-level",
            "ERROR",
        ],
        cwd=str(ROOT),
    )
    time.sleep(0.5)
    noise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    joiner = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    joiner.settimeout(2.0)
    try:
        noise.sendto(b"not-a-valid-packet", ("127.0.0.1", game_port))
        joiner.sendto(protocol.pack_conn("Survivor"), ("127.0.0.1", game_port))
        ok = False
        end = time.monotonic() + 2.5
        while time.monotonic() < end:
            try:
                data, _addr = joiner.recvfrom(protocol.RECV_BUF)
            except socket.timeout:
                continue
            if protocol.tag_of(data) == protocol.CONOK:
                ok = True
                break
        assert ok, "Server did not respond with CONOK after garbage packet"
    finally:
        noise.close()
        joiner.close()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
