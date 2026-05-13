# Skyward Race LAN Multiplayer

Skyward Race LAN Multiplayer is a real-time 2D tower-racing game built with
Python and pygame-ce for CS323 - Parallel and Distributed Computing. Players
host or join LAN rooms, ready up in a lobby, race upward through generated
platform levels, and compare results after each match.

The project focuses on practical distributed-systems concepts in a game setting:
UDP networking, LAN discovery, client/server state synchronization, concurrent
network threads, shared state protection, reconnect recovery, and runtime
performance telemetry.

Current app version is defined in [app/version.py](app/version.py). Run
`python main.py --version` to print the exact version and build number.

## Features

- LAN room hosting, browsing, direct joining, and room closing.
- Server-authoritative lobby and match state over UDP.
- Ready checks, countdown start/cancel, host kick controls, and room name/level selection.
- Real-time player synchronization with local input, remote animations, orb effects, and platform progress.
- Customizable player profile, avatar head, model color, fullscreen/scale, control scheme, and metrics toggle.
- Avatar transfer with compressed payloads, model-only metadata, replay for late joiners, and rematch cache retention.
- Match results with placements, elapsed time, platform progress, avatars, and automatic return to lobby.
- Reconnect tickets, pause/resume handling, spectator recovery, and stale packet rejection.
- FPS, RTT, packet loss, throughput, packet rate, and packet-tag diagnostics in overlay and logs.
- PyInstaller onedir build support for Windows distribution.

## PDC Relevance

| Concept | Implementation |
| --- | --- |
| Distributed clients | Each player runs a separate game client with local rendering/input and network event handling. |
| Server-authoritative coordination | `network/server.py` owns room state, match state, eliminations, results, and validation. |
| Message passing | UDP packets are packed/unpacked in `network/protocol.py` and sent with Python sockets. |
| Concurrency | Client receiver, heartbeat, discovery, presence, beacon, and server loops run in separate threads/processes. |
| Shared state synchronization | `network/room_state.py` centralizes players, readiness, positions, alive state, reconnect data, and standings. |
| Synchronization mechanisms | Locks, queues, thread events, and monotonic timers protect shared data and coordinate background work. |
| Performance evaluation | Built-in overlay and logs report FPS, latency/RTT, heartbeat loss, packet rates, and network throughput. |

## Requirements

- Python 3.10 or newer.
- Windows is the primary packaged-build target.
- Runtime dependency: `pygame-ce==2.5.2`.
- Development/build dependency: `pyinstaller>=6.0`.

Install runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

Install test/build dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Use `pygame-ce`, not the legacy `pygame` package.

## Quick Start

Run from the project root so assets and local paths resolve correctly:

```bash
python main.py
```

The normal flow is:

1. Choose or load a player profile.
2. Select or edit an avatar/model.
3. Host a room or browse LAN rooms.
4. Ready up, start countdown, race, view results, and return to lobby.

### Host From CLI

```bash
python main.py --host --name KURT --room "Game Room"
```

### Direct Join

Use this when discovery is blocked, when using a tunnel such as playit.gg, or
when joining by known host address:

```bash
python main.py --name Player2 --server 192.168.1.10:5555
```

The value must be `HOST:PORT`.

### Development Profiles

Use `--dev` when running multiple local instances on one machine:

```bash
python main.py --dev
```

The packaged build also includes `dev.bat` beside the exe for quick multi-window
testing.

### Logs

Client logs are written to:

```text
logs/<timestamp>-<player>/client.log
```

Hosted rooms also create:

```text
logs/<timestamp>-<player>/server.log
```

In PyInstaller builds, logs are created beside `SkywardRaceLAN.exe`. In source
runs, logs are created under the repository root.

Use verbose logging when diagnosing network behavior:

```bash
python main.py --log-level DEBUG
```

## Controls

| Context | Input | Action |
| --- | --- | --- |
| Menu/lobby/results | Mouse | Buttons, room cards, settings, ready/start, kick, return |
| In game | A / D | Move left/right |
| In game | W | Jump |
| Settings | Control scheme toggle | Switch movement between WASD and arrow-key layouts |
| Settings | Metrics toggle | Show or hide FPS/network metrics overlay |

## Networking

| Port | Protocol | Purpose |
| --- | --- | --- |
| 5555 | UDP | Room, lobby control, gameplay, avatar transfer, heartbeat, reconnect |
| 5556 | UDP broadcast | LAN room discovery and presence |

Notes:

- Hosts run a local server subprocess, then connect to it like any other client.
- Joiners normally discover rooms by UDP broadcast on the same LAN.
- Direct join bypasses discovery but still requires UDP traffic to reach the host.
- Campus, guest, or public Wi-Fi may block peer-to-peer traffic through AP/client isolation.
- Windows Defender Firewall may need private-network access for Python or the packaged exe.

## Performance Metrics

The in-game/settings-controlled overlay and logs expose:

- FPS.
- RTT/ping EMA, rolling average/min/max, jitter, p50, p95, session average/min/max.
- Heartbeat sent/acked/lost and loss percentage.
- Inbound/outbound KiB/s current/average/min/max.
- Packet rates and packet tags per second, such as `PSTA`, `HRTB`, `HBAK`, `AVHD`, and `AVCK`.

These metrics support the academic evaluation requirement for response time,
latency, throughput, and runtime performance evidence. For report generation,
see [tools/brochure_performance.py](tools/brochure_performance.py).

## Building A Windows Distribution

Prebuilt Windows packages may be distributed as zip artifacts. Download or share
the full zip package for a release/build, then extract it before running
`SkywardRaceLAN.exe`.

Install development dependencies first:

```powershell
python -m pip install -r requirements-dev.txt
```

Build the executable folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Output:

```text
dist\SkywardRaceLAN\SkywardRaceLAN.exe
```

Distribute the whole `dist\SkywardRaceLAN\` folder, not just the exe. The
`_internal` folder contains bundled assets and runtime dependencies. A good
manual package artifact name is:

```text
SkywardRaceLAN-v<semver>-build-<build>.zip
```

Before distributing a packaged build, update `VERSION_MAJOR`,
`VERSION_MINOR`, `VERSION_PATCH`, and/or `BUILD_NUMBER` in
[app/version.py](app/version.py).

## Testing

Run the full test suite:

```bash
python -m pytest tests -q
```

Run quick tests without subprocess/loopback integration checks:

```bash
python -m pytest tests -q -m "not integration"
```

Run only integration checks:

```bash
python -m pytest tests -q -m integration
```

The suite covers protocol encoding/decoding, malformed packets, room state,
cooldowns, end policy, lobby integration, reconnect recovery, avatar assembly,
network metrics, UI helpers, results rendering, and gameplay edge cases.

## Useful Tools

```bash
python tools/list_rooms.py
python tools/scripted_lobby.py --help
python tools/brochure_performance.py --help
```

- `list_rooms.py` inspects LAN discovery beacons.
- `scripted_lobby.py` drives lobby/gameplay protocol scenarios.
- `brochure_performance.py` produces performance evidence for reports.

## Project Structure

```text
app/                 Application context, display, profile, logging, versioning
assets/              Sprites, UI frames, fonts, maps, and game art
network/             Protocol, UDP client/server, discovery, room state, reconnect
player_scripts/      Player physics, animation, avatar/model assets
states/              Menu, avatar setup, browse lobby, host/join lobby, game, results
ui/                  Theme, widgets, HUD, metrics overlay, results table
world/               Level generation, constants, assets, camera
tools/               Manual diagnostics and performance/report helpers
scripts/             Build and packaged-dev helpers
tests/               Pytest unit and integration coverage
```

## Troubleshooting

| Symptom | Likely cause | What to try |
| --- | --- | --- |
| Joiner sees no rooms | UDP broadcast blocked or different subnet | Use the same private LAN, allow firewall access, or direct join with `--server`. |
| Direct join fails | Wrong host/port or UDP tunnel not mapped | Verify host address, port forwarding/tunnel, and server log. |
| Address already in use | Another server is bound to UDP 5555/5556 | Close duplicate instances or restart the old packaged build. |
| Missing assets in packaged build | Only the exe was copied | Copy or zip the whole `dist\SkywardRaceLAN\` folder. |
| Avatars missing | Late packet, stale cache, or interrupted transfer | Check `AVHD`/`AVCK` entries in logs; reconnect/rematch paths now replay and cache avatar metadata. |
| High ping or packet loss | Tunnel route, Wi-Fi interference, or blocked UDP | Compare direct LAN vs tunnel logs and inspect RTT/loss/throughput metrics. |
| Player not eliminated or result delayed | Terminal packet loss | Current clients resend pending DEAD/GOAL until server confirmation. |

## License And Course Use

Academic project for CS323 - Parallel and Distributed Computing.
