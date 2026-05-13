"""
Reproducible performance samples for brochures / demos (Tower Jump LAN).

Run from repo root:

    python tools/brochure_performance.py

Optional: skip multi-client benchmarks (faster):

    python tools/brochure_performance.py --skip-server-load

Tunable: `--load-rounds-lobby`, `--load-rounds-game`, `--load-warmup` (2-player vs 5-player lobby idle
heartbeats and in-game PSTA fan-out measured on localhost with the real `LobbyServer`).

Produces console output plus an optional Markdown table row block you can paste
into documentation. Numbers are hardware-dependent - always rerun on the machine
you are reporting and mention CPU/OS in the brochure footnote.

This does not substitute for production profiling under real multi-player LAN
load; it gives concrete quantitative evidence alongside your architecture story.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow `python tools/brochure_performance.py` without PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import platform
import socket
import statistics
import threading
import time

from network import protocol
from network.protocol import pack_player_state, safe_unpack_player_state
from network.room_state import RoomState
from network.server import LobbyServer
from world.level_system import generate_level


def _bench_pack_unpack_player_state(iterations: int) -> tuple[float, float]:
    payload = pack_player_state(128.5, -40.25, player_id=2, animation_state="idle_front")

    def work() -> None:
        data = payload
        for _ in range(iterations):
            p = safe_unpack_player_state(data)
            if p is None:
                raise RuntimeError("unpack failed")
            _tag, x, y, pid, sid = p
            data = pack_player_state(float(x), float(y), int(pid), int(sid))

    t0 = time.perf_counter()
    work()
    dt = max(time.perf_counter() - t0, 1e-12)

    throughput = iterations / dt
    per_pkt_us = (dt / iterations) * 1e6
    # Final round differs slightly; benchmarks use iterative transform for pressure.
    return throughput, per_pkt_us


def _bench_level_generation(samples: int) -> tuple[float, float, float]:
    # Fixed seeds for repeatable measurement; sweep level IDs for variability.
    level_ids = tuple(protocol.LEVEL_IDS)
    times_ms: list[float] = []
    i = 0
    seed = 9_871_239
    while i < samples:
        for lid in level_ids:
            seed = (seed * 1_103_515_245 + 12_345) & 0xFFFFFFFF
            t0 = time.perf_counter()
            generate_level(level_id=lid, seed=int(seed))
            elapsed_ms = (time.perf_counter() - t0) * 1_000
            times_ms.append(elapsed_ms)
            i += 1
            if i >= samples:
                break
    return statistics.median(times_ms), statistics.mean(times_ms), max(times_ms)


def _udp_loopback_rtt(samples: int) -> tuple[float, float, float, float]:
    """Median / min / mean / max round-trip microseconds for UDP echo on 127.0.0.1."""

    echo_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    echo_sock.bind(("127.0.0.1", 0))
    echo_port = echo_sock.getsockname()[1]
    stop_echo = threading.Event()

    def echo_loop() -> None:
        echo_sock.settimeout(0.05)
        while not stop_echo.is_set():
            try:
                data, addr = echo_sock.recvfrom(protocol.RECV_BUF)
            except TimeoutError:
                continue
            try:
                echo_sock.sendto(data, addr)
            except OSError:
                pass

    thread = threading.Thread(target=echo_loop, name="udp-echo", daemon=True)
    thread.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(5.0)
    payload = pack_player_state(10.0, 20.0, 3, "walk_right")
    server_addr = ("127.0.0.1", echo_port)
    rt_us: list[float] = []

    # Warm UDP path
    client.sendto(payload, server_addr)
    client.recv(protocol.RECV_BUF)

    try:
        for _ in range(samples):
            c0 = time.perf_counter()
            client.sendto(payload, server_addr)
            client.recv(protocol.RECV_BUF)
            rt_us.append((time.perf_counter() - c0) * 1e6)
    finally:
        stop_echo.set()
        thread.join(timeout=2.0)
        client.close()
        echo_sock.close()

    return statistics.median(rt_us), min(rt_us), statistics.mean(rt_us), max(rt_us)


@dataclass
class _BenchClient:
    sock: socket.socket
    player_id: int
    session_token: int


def _drain_udp(sock: socket.socket) -> None:
    sock.setblocking(False)
    try:
        while True:
            sock.recvfrom(65535)
    except BlockingIOError:
        pass


def _pump_server(server: LobbyServer) -> None:
    """Drain server RX queue and tick (mirrors network/server.py main loop pattern)."""
    while True:
        try:
            data, addr = server.sock.recvfrom(protocol.RECV_BUF)
        except BlockingIOError:
            break
        server.handle_packet(data, addr)
        server.tick()
    server.tick()


def _player_names(player_count: int) -> list[str]:
    if player_count < protocol.MIN_PLAYERS or player_count > protocol.MAX_PLAYERS:
        raise ValueError(f"player_count must be {protocol.MIN_PLAYERS}-{protocol.MAX_PLAYERS}, got {player_count}")
    names = ["HostBrch01"]
    names.extend([f"GstBrch{i:02d}" for i in range(2, player_count + 1)])
    return names


def _make_bench_server() -> tuple[LobbyServer, tuple[str, int]]:
    game_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    game_sock.bind(("127.0.0.1", 0))
    game_sock.setblocking(False)
    _host, game_port = game_sock.getsockname()
    server_addr = ("127.0.0.1", int(game_port))
    room = RoomState("BrochBench", int(game_port))
    server = LobbyServer(
        sock=game_sock,
        room_state=room,
        countdown_seconds=5.0,
        reconnect_grace_seconds=30.0,
        player_timeout_seconds=60.0,
        lobby_player_timeout_seconds=120.0,
    )
    setattr(server, "_beacon_broadcaster", None)
    return server, server_addr


def _setup_clients(server: LobbyServer, server_addr: tuple[str, int], player_count: int) -> list[_BenchClient]:
    clients: list[_BenchClient] = []
    for pname in _player_names(player_count):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.setblocking(False)
        sock.sendto(protocol.pack_conn(pname), server_addr)
        _pump_server(server)
        player_id = -1
        session_token = -1
        try:
            while True:
                data, _addr = sock.recvfrom(protocol.RECV_BUF)
                unpacked = protocol.safe_unpack_session(data)
                if unpacked is not None:
                    _tag, player_id, session_token = unpacked
        except BlockingIOError:
            pass
        if player_id < 0:
            raise RuntimeError(f"benchmark: no SESSION for player {pname!r}")
        clients.append(_BenchClient(sock=sock, player_id=player_id, session_token=int(session_token)))
        _drain_udp(sock)
    return clients


def _enter_in_game(server: LobbyServer, server_addr: tuple[str, int], clients: list[_BenchClient]) -> None:
    host = clients[0]
    for c in clients[1:]:
        c.sock.sendto(protocol.pack_ready(c.player_id, True), server_addr)
        _pump_server(server)
        _drain_udp(c.sock)
    host.sock.sendto(protocol.pack_start(host.player_id, protocol.START_ACTION_START), server_addr)
    _pump_server(server)
    for c in clients:
        _drain_udp(c.sock)

    server.room_state.countdown_deadline = time.monotonic() - 1.0
    for _ in range(250):
        _pump_server(server)
        if server.room_state.state == protocol.STATE_IN_GAME:
            break
    else:
        raise RuntimeError("benchmark: failed to reach STATE_IN_GAME")

    # Let reliable GSTART rebroadcast queue drain (real server uses timed rebroadcasts).
    t0 = time.perf_counter()
    while server._reliable_broadcasts and time.perf_counter() - t0 < 4.0:
        time.sleep(0.04)
        _pump_server(server)
    for c in clients:
        _drain_udp(c.sock)


def _teardown_bench(server: LobbyServer, clients: list[_BenchClient]) -> None:
    try:
        server.sock.close()
    except OSError:
        pass
    for c in clients:
        try:
            c.sock.close()
        except OSError:
            pass


def _bench_server_lobby_idle(
    player_count: int, rounds: int, warmup: int
) -> tuple[float, float]:
    """Synchronized rounds: each player sends one heartbeat; server processes batch. Returns (elapsed_s, ms_per_round)."""
    logging.disable(logging.CRITICAL)
    server, server_addr = _make_bench_server()
    clients: list[_BenchClient] = []
    try:
        clients = _setup_clients(server, server_addr, player_count)
        cd_id = server._countdown_id
        mid = server._match_id

        def one_round() -> None:
            for c in clients:
                c.sock.sendto(
                    protocol.pack_heartbeat(
                        c.player_id,
                        c.session_token,
                        protocol.CLIENT_STATE_LOBBY,
                        cd_id,
                        mid,
                    ),
                    server_addr,
                )
            _pump_server(server)
            for c in clients:
                _drain_udp(c.sock)

        for _ in range(max(0, warmup)):
            one_round()
        t0 = time.perf_counter()
        for _ in range(rounds):
            one_round()
        dt = max(time.perf_counter() - t0, 1e-12)
    finally:
        _teardown_bench(server, clients)
        logging.disable(logging.NOTSET)
    per_round_ms = (dt / rounds) * 1_000.0
    return dt, per_round_ms


def _bench_server_in_game_psta(
    player_count: int, rounds: int, warmup: int
) -> tuple[float, float]:
    """In-game: each player sends one PSTA per round (server rebroadcasts to peers)."""
    logging.disable(logging.CRITICAL)
    server, server_addr = _make_bench_server()
    clients: list[_BenchClient] = []
    try:
        clients = _setup_clients(server, server_addr, player_count)
        _enter_in_game(server, server_addr, clients)

        def one_round(step: int) -> None:
            for idx, c in enumerate(clients):
                c.sock.sendto(
                    pack_player_state(110.0 + 0.02 * step, 180.0 - float(idx), c.player_id, "walk_right"),
                    server_addr,
                )
            _pump_server(server)
            for c in clients:
                _drain_udp(c.sock)

        for w in range(max(0, warmup)):
            one_round(w)
        t0 = time.perf_counter()
        for r in range(rounds):
            one_round(warmup + r)
        dt = max(time.perf_counter() - t0, 1e-12)
    finally:
        _teardown_bench(server, clients)
        logging.disable(logging.NOTSET)
    per_round_ms = (dt / rounds) * 1_000.0
    return dt, per_round_ms


def _fmt_load_compare(samples: dict[int, float], rounds: int, subtitle: str) -> str:
    t2 = samples[2]
    t5 = samples[5]
    ratio = (t5 / t2) if t2 > 1e-12 else float("nan")
    return (
        f"{subtitle}: 2-player ~ {t2:.3f} ms per sync round ({rounds} timed rounds); "
        f"5-player ~ {t5:.3f} ms; 5p/2p wall-time ratio ~ {ratio:.2f}x "
        "(all players send one packet per round; real UDP localhost)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Print brochure-ready performance snapshot")
    parser.add_argument("--iter-packet", type=int, default=500_000, help="Pack/unpack iterations")
    parser.add_argument("--iter-level", type=int, default=150, help="Level generation iterations")
    parser.add_argument("--iter-rtt", type=int, default=3_000, help="UDP loopback RTT samples")
    parser.add_argument(
        "--skip-server-load",
        action="store_true",
        help="Skip localhost multi-client lobby/in-game benchmarks (faster CI / smoke runs)",
    )
    parser.add_argument("--load-warmup", type=int, default=4, help="Warmup rounds before timing server-load benches")
    parser.add_argument("--load-rounds-lobby", type=int, default=250, help="Timed lobby-idle rounds (all players heartbeat)")
    parser.add_argument("--load-rounds-game", type=int, default=80, help="Timed in-game PSTA rounds (all players)")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown snippet for brochures")
    args = parser.parse_args()

    uni = platform.uname()

    pkt_s, pkt_us = _bench_pack_unpack_player_state(args.iter_packet)
    lev_med, lev_mean, lev_max = _bench_level_generation(args.iter_level)
    rtt_med, rtt_min, rtt_mean, rtt_max = _udp_loopback_rtt(args.iter_rtt)

    load_lobby_ms: dict[int, float] = {}
    load_game_ms: dict[int, float] = {}
    if not args.skip_server_load:
        for n in (2, 5):
            _dt, ms_r = _bench_server_lobby_idle(n, args.load_rounds_lobby, args.load_warmup)
            load_lobby_ms[n] = ms_r
        for n in (2, 5):
            _dt, ms_r = _bench_server_in_game_psta(n, args.load_rounds_game, args.load_warmup)
            load_game_ms[n] = ms_r

    lines = [
        "Tower Jump LAN - performance snapshot (run locally with your brochure hardware)",
        f"Machine: {uni.system} {uni.release}; {uni.machine}; Python {platform.python_version()}",
        "",
        "--- Measured ---",
        f"Protocol: player-state (PSTA) encode+decode throughput ~ {pkt_s / 1e6:.2f} M ops/sec  ({pkt_us:.2f} us per iterative round-trip in-process)",
        f"Gameplay: procedural `generate_level` (all level IDs, fixed seed stream) "
        f"median ~ {lev_med:.2f} ms; mean ~ {lev_mean:.2f} ms; worst-sample ~ {lev_max:.2f} ms  (n={args.iter_level})",
        f"Networking: localhost UDP echo RTT median ~ {rtt_med:.0f} us; "
        f"min/mean/max ~ {rtt_min:.0f} / {rtt_mean:.0f} / {rtt_max:.0f} us  ({args.iter_rtt} samples, PSTA-sized payload)",
        "",
    ]

    if not args.skip_server_load:
        lines.extend(
            [
                "--- Under load (authoritative LAN server + real UDP stack, localhost) ---",
                _fmt_load_compare(load_lobby_ms, args.load_rounds_lobby, "Lobby idle heartbeats"),
                _fmt_load_compare(load_game_ms, args.load_rounds_game, "In-game PSTA (server rebroadcasts to peers)"),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "--- Under load ---",
                "(omitted; run without --skip-server-load to benchmark 2p vs 5p lobby/in-game rounds)",
                "",
            ]
        )

    lines.extend(
        [
            "--- Architecture (fixed by design - cite separately) ---",
            "- Client render loop capped at ~60 FPS; player input + networking run on background threads.",
            "- Authoritative LAN server: UDP gameplay + timed ticks (countdown / in-game pause / timeouts).",
            "- Lightweight binary wire format (packed structs); small packets suitable for LAN.",
        ]
    )

    text = "\n".join(lines) + "\n"
    print(text, end="")

    if args.markdown:
        print("--- Paste into brochure ---\n")
        print("| Metric | Value | Notes |")
        print("| --- | --- | --- |")
        print(f"| Player-state marshal | **{pkt_s / 1e6:.2f} M ops/sec** | single-process Python loop ({args.iter_packet} iters) |")
        print(
            f"| Level generation time | **{lev_med:.1f} ms** median ({lev_max:.1f} ms max sample) "
            f"| procedural, {args.iter_level} generations; seed sweep |"
        )
        print(
            f"| Localhost UDP RTT | **~{rtt_med:.0f} us** median | echo of PSTA-sized packet; LAN baseline order-of-magnitude |"
        )
        print("| Client frame pacing | **60 FPS cap** | `pygame`; network recv on daemon thread |")
        print("| Wire format | Compact structs | Typical gameplay packets tens of bytes |")
        if not args.skip_server_load:
            t2l = load_lobby_ms[2]
            t5l = load_lobby_ms[5]
            t2g = load_game_ms[2]
            t5g = load_game_ms[5]
            rl = f"{args.load_rounds_lobby} rounds"
            rg = f"{args.load_rounds_game} rounds"
            print(
                f"| Lobby load (heartbeat) | **2p {t2l:.2f} ms** vs **5p {t5l:.2f} ms** / sync round ({rl}) | "
                f"5p/2p ~ {(t5l/t2l) if t2l else 0:.2f}x; idle room |"
            )
            print(
                f"| In-game load (PSTA + fan-out) | **2p {t2g:.2f} ms** vs **5p {t5g:.2f} ms** / sync round ({rg}) | "
                f"5p/2p ~ {(t5g/t2g) if t2g else 0:.2f}x; localhost UDP |"
            )
        foot = f"*Measured on `{uni.system}` / Python {platform.python_version()}; rerun on target hardware.*"
        print()
        print(foot)


if __name__ == "__main__":
    main()
