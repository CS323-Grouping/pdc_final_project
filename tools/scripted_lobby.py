import argparse
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from network import protocol


class FakeClient:
    def __init__(self, name: str, host: str, port: int):
        self.name = name
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.2)
        self.player_id = -1
        self.events: List[Tuple[str, object]] = []

    def close(self):
        self.sock.close()

    def send(self, payload: bytes):
        self.sock.sendto(payload, self.addr)

    def connect(self) -> Tuple[bool, Optional[int], Optional[int]]:
        self.send(protocol.pack_conn(self.name))
        end = time.monotonic() + 2.5
        denied_reason = None
        denied_extra = None
        while time.monotonic() < end:
            try:
                data, _ = self.sock.recvfrom(protocol.RECV_BUF)
            except socket.timeout:
                continue

            tag = protocol.tag_of(data)
            if tag == protocol.CONOK:
                unpacked = protocol.safe_unpack_conok(data)
                if unpacked is None:
                    continue
                _tag, player_id, _room_name = unpacked
                self.player_id = player_id
                return True, None, None
            if tag == protocol.CONNO:
                unpacked = protocol.safe_unpack_conno(data)
                if unpacked is None:
                    continue
                _tag, denied_reason, denied_extra = unpacked
                return False, denied_reason, denied_extra
        return False, denied_reason, denied_extra

    def send_ready(self, ready: bool):
        self.send(protocol.pack_ready(self.player_id, ready))

    def send_start(self):
        self.send(protocol.pack_start(self.player_id))

    def send_dead(self):
        self.send(protocol.pack_dead(self.player_id, 0))

    def send_kick(self, target_id: int):
        self.send(protocol.pack_kick(self.player_id, target_id))

    def pump(self, duration_seconds: float):
        end = time.monotonic() + duration_seconds
        while time.monotonic() < end:
            try:
                data, _ = self.sock.recvfrom(protocol.RECV_BUF)
            except socket.timeout:
                continue

            tag = protocol.tag_of(data)
            if tag == protocol.CDWN:
                unpacked = protocol.safe_unpack_cdwn(data)
                if unpacked is not None:
                    self.events.append(("CDWN", unpacked[1]))
            elif tag == protocol.GSTART:
                self.events.append(("GSTART", None))
            elif tag == protocol.ELIM:
                unpacked = protocol.safe_unpack_elim(data)
                if unpacked is not None:
                    self.events.append(("ELIM", (unpacked[1], unpacked[2])))
            elif tag == protocol.GEND:
                unpacked = protocol.safe_unpack_gend(data)
                if unpacked is not None:
                    self.events.append(("GEND", unpacked))
            elif tag == protocol.KICKED:
                unpacked = protocol.safe_unpack_kicked(data)
                if unpacked is not None:
                    self.events.append(("KICKED", unpacked[1]))
            elif tag == protocol.LIST:
                unpacked = protocol.safe_unpack_list(data)
                if unpacked is not None:
                    self.events.append(("LIST", unpacked))


def _event_markers(clients: List[FakeClient]) -> Dict[int, int]:
    return {id(client): len(client.events) for client in clients}


def wait_for_event(clients: List[FakeClient], event_name: str, timeout_seconds: float, markers: Optional[Dict[int, int]] = None) -> bool:
    end = time.monotonic() + timeout_seconds
    markers = markers or _event_markers(clients)
    while time.monotonic() < end:
        for client in clients:
            client.pump(0.1)
            start_idx = markers.get(id(client), 0)
            if any(evt == event_name for evt, _payload in client.events[start_idx:]):
                return True
    return False


def run_script(host: str, port: int, discovery_port: int):
    server = subprocess.Popen(
        [
            sys.executable,
            str(PROJECT_ROOT / "network" / "server.py"),
            "--host",
            host,
            "--port",
            str(port),
            "--discovery-port",
            str(discovery_port),
            "--room",
            "Phase2Room",
            "--log-level",
            "ERROR",
        ],
        cwd=str(PROJECT_ROOT),
    )

    clients: List[FakeClient] = []
    try:
        time.sleep(0.7)
        host_client = FakeClient("HostAAA", host, port)
        join_1 = FakeClient("JoinBBB", host, port)
        join_2 = FakeClient("JoinCCC", host, port)
        join_3 = FakeClient("JoinDDD", host, port)
        clients = [host_client, join_1, join_2, join_3]

        for client in clients:
            ok, reason, extra = client.connect()
            assert ok, f"{client.name} failed to connect: reason={reason}, extra={extra}"

        join_1.send_ready(True)
        join_2.send_ready(True)
        join_3.send_ready(True)
        markers = _event_markers(clients)
        host_client.send_start()
        assert wait_for_event(clients, "GSTART", 8.0, markers), "Did not receive GSTART after countdown"
        assert any(evt == "CDWN" for evt, _ in host_client.events), "Did not receive CDWN countdown broadcast"

        markers = _event_markers(clients)
        join_3.send_dead()
        time.sleep(0.2)
        join_2.send_dead()
        time.sleep(0.2)
        join_1.send_dead()
        assert wait_for_event(clients, "GEND", 3.0, markers), "No GEND after elimination sequence"
        gend_events = [payload for evt, payload in host_client.events if evt == "GEND"]
        assert gend_events, "Missing GEND payload"
        reason_code, standings = gend_events[-1]
        assert reason_code == protocol.GEND_REASON_NORMAL, "Unexpected GEND reason"
        assert len(standings) == 4, "Standings should include 4 players"

        join_1.send_ready(True)
        join_2.send_ready(True)
        join_3.send_ready(True)
        markers = _event_markers(clients)
        host_client.send_start()
        assert wait_for_event(clients, "GSTART", 8.0, markers), "Second round did not start"

        # Restart into a fresh lobby-only scenario for deterministic kick/cooldown checks.
        for client in clients:
            client.close()
        clients = []
        server.terminate()
        server.wait(timeout=3)

        server = subprocess.Popen(
            [
                sys.executable,
                str(PROJECT_ROOT / "network" / "server.py"),
                "--host",
                host,
                "--port",
                str(port),
                "--discovery-port",
                str(discovery_port),
                "--room",
                "Phase2Room",
                "--log-level",
                "ERROR",
            ],
            cwd=str(PROJECT_ROOT),
        )
        time.sleep(0.7)

        host_kick = FakeClient("HostAAA", host, port)
        join_kick = FakeClient("JoinBBB", host, port)
        clients = [host_kick, join_kick]
        ok, reason, extra = host_kick.connect()
        assert ok, f"Host reconnect failed: reason={reason}, extra={extra}"
        ok, reason, extra = join_kick.connect()
        assert ok, f"Joiner reconnect failed: reason={reason}, extra={extra}"

        host_kick.send_kick(join_kick.player_id)
        join_kick.pump(1.5)
        assert any(evt == "KICKED" for evt, _ in join_kick.events), "First kick did not notify target"
        join_kick.close()

        # First kick has zero cooldown; reconnect should succeed.
        join_1_rejoin = FakeClient("JoinBBB", host, port)
        ok, reason, extra = join_1_rejoin.connect()
        assert ok, f"First rejoin should succeed (reason={reason}, extra={extra})"

        host_kick.send_kick(join_1_rejoin.player_id)
        join_1_rejoin.pump(1.5)
        join_1_rejoin.close()

        join_1_blocked = FakeClient("JoinBBB", host, port)
        ok, reason, extra = join_1_blocked.connect()
        assert not ok, "Second immediate rejoin should be blocked by cooldown"
        assert reason == protocol.CONNO_REASON_COOLDOWN, f"Expected cooldown reject, got {reason}"
        assert 10 <= (extra or 0) <= 15, f"Expected cooldown ~15s, got extra={extra}"
        join_1_blocked.close()

        invalid = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "network" / "server.py"),
                "--host",
                host,
                "--port",
                str(port + 1),
                "--room",
                "Bad Room!",
                "--log-level",
                "ERROR",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        assert invalid.returncode != 0, "Invalid room name should fail server bootstrap"
        assert "Invalid room name" in (invalid.stdout + invalid.stderr), "Expected clear invalid room error message"

        print("Phase 2 scripted lobby checks passed.")
    finally:
        for client in clients:
            try:
                client.close()
            except Exception:
                pass
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()


def parse_args():
    parser = argparse.ArgumentParser(description="Scripted Phase 2 lobby protocol smoke test")
    parser.add_argument("--host", default="127.0.0.1", help="Server host to bind and test against")
    parser.add_argument("--port", type=int, default=5590, help="Temporary game port for the scripted server")
    parser.add_argument("--discovery-port", type=int, default=5591, help="Temporary discovery port for the scripted server")
    return parser.parse_args()


def main():
    args = parse_args()
    run_script(args.host, args.port, args.discovery_port)


if __name__ == "__main__":
    main()
