# Tower-Jumping LAN Multiplayer (CS323 PDC Final)

A small **pygame-ce** platformer with **UDP LAN lobby**: discovery on port **5556**, gameplay / lobby control on **5555** (default). No hardcoded LAN IP for normal play—hosts advertise rooms via beacons; joiners browse and connect.

**Dependency:** install **`pygame-ce`** (Community Edition), not the classic `pygame` package:

```bash
pip install -r requirements.txt
```

Use **Python 3.10+**. Networking uses the standard library only (`socket`, `struct`, `threading`).

## Quick start

From the project root (so `assets/` paths resolve):

### Menu (typical)

```bash
python main.py
```

Enter an **alphanumeric player name** (3–24 characters), then **Host Room** or **Join Room**.

### Host (CLI shortcut)

```bash
python main.py --host --name YourName --room YourRoomName
```

Room names must match `^[A-Za-z0-9]{3,24}$`.

### Join without discovery (emergency / AP isolation)

```bash
python main.py --name YourName --server 192.168.1.10:5555
```

### Verbose logs

```bash
python main.py --log-level DEBUG
```

The dedicated server process supports the same flag:

```bash
python network/server.py --room MyRoom --log-level DEBUG
```

## Host vs joiner

| Role   | What runs |
|--------|-----------|
| **Host** | `main.py` starts a **subprocess** `network/server.py`, then connects to `127.0.0.1:5555` like any client. |
| **Joiner** | `main.py` only runs the client; discovery listens on **5556** while browsing. |

## Controls (in-game)

| Input | Action |
|-------|--------|
| **A** / **D** | Move |
| **W** | Jump (when on a platform) |
| Window | Resizable |

Lobby screens use the **mouse** for buttons, room cards, ready, kick, etc.

## Ports and firewall

| Port  | Role |
|------|------|
| **5555** | Game / lobby UDP (host binds here). |
| **5556** | Discovery beacons (all LAN listeners; must not be blocked for browse). |

On **Windows**, the first time Python listens on UDP, **Windows Defender Firewall** may prompt—allow access on **private** networks for the demo. If joiners never see rooms, check that **both** ports are allowed for Python.

## Wi-Fi / AP isolation

Some campus or guest Wi-Fi networks use **client isolation** (devices cannot see each other). Discovery **will not work** on those SSIDs. Mitigations:

- Use a **phone hotspot** or a known “game LAN” where device-to-device traffic is allowed.
- Or use **`--server HOST:PORT`** so the joiner connects directly by IP (still needs the router to allow UDP between clients).

## Testing

Automated tests use **pytest**. Bytecode under `tests/` is discouraged: `tests/conftest.py` sets `sys.dont_write_bytecode = True`, and `.gitignore` excludes `__pycache__` / `*.pyc`.

```bash
# Fast unit tests (no subprocess server)
python -m pytest tests -q -m "not integration"

# Full suite including loopback UDP smoke tests (starts `network/server.py`)
python -m pytest tests -q
```

Coverage includes **protocol** round-trips and malformed packets, **discovery** TTL + beacon version filtering, **room state / cooldown / end policy**, **UI animations**, and **integration** checks (sixth player rejected, garbage datagram does not kill the server).

A richer scripted flow (countdown, `GSTART`, eliminations) is available via:

```bash
python tools/scripted_lobby.py --help
python tools/list_rooms.py
```

## Manual smoke / acceptance

For course demos, use the **manual matrix** in `docs/implementationPlan/lan_lobby_implementation_plan.md` (§9.3, cases M1–M20): multi-client scenarios, kick/cooldown, countdown, two rooms on one LAN, etc.

## Report / demo checklist (Phase 5)

1. Record a **short demo video** (host + at least one joiner on your LAN or loopback).  
2. Capture **screenshots** of: main menu, browse lobby, host lobby, joined lobby, in-game, results.  
3. Keep **`readme.md`** with the class; cite the implementation plan for protocol details.

## Project layout (high level)

- `main.py` — Entry; CLI flags; pygame bootstrap.  
- `app/state_machine.py` — Global app context, server subprocess, network attach/detach.  
- `states/` — Menu, browse, host/joined lobby, in-game, results.  
- `network/` — `protocol.py`, `server.py`, `discovery.py`, `beacon.py`, `room_state.py`, `network_handler.py`, etc.  
- `ui/` — Theme, components, animations.  
- `tests/` — Pytest suite.  
- `docs/` — Analysis and implementation plan.

## Troubleshooting

| Symptom | Things to try |
|---------|----------------|
| Joiner sees **no rooms** | Same subnet? Firewall? AP isolation? Try hotspot; or `--server IP:5555`. |
| **Address already in use** | Another host is on 5555/5556; close other instances or change `--port` / discovery (advanced). |
| **Could not start server** | Port 5555 taken; stop duplicate `server.py` or other app using UDP 5555. |
| Kicked / room closed | Red **banner** on main menu explains; cooldown re-join shows remainings or “session blocked”. |

## License / course use

Academic project (CS323 — Parallel and Distributed Computing).
