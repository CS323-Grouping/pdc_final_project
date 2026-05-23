# Skyward Race — Port Plan

The pygame original is the parity target, not the implementation target. We want the *same feel* with idiomatic Godot under the hood.

## Locked-in Godot project config

(Decided 2026-05-17, see auto-memory.)

| Setting | Value |
| --- | --- |
| Godot version | 4.6.2 stable (`C:\Program Files (x86)\Godot\Godot_v4.6.2-stable_win64.exe`) |
| Internal resolution | 320×180 (scales clean to 1080p/1440p/4K) |
| Stretch mode | `canvas_items` (NOT `viewport`) |
| Stretch aspect | `keep` (letterbox to maintain 16:9 if user resizes off-aspect) |
| Scale mode | `integer` (only 1×/2×/3×/… scales, no fractional blurriness) |
| Resizable window | `true` |
| Min window size | 320×180 (enforced in `Settings._ready()` via `DisplayServer.window_set_min_size`) |
| Fullscreen toggle | F11 / Alt+Enter (global handler in `Settings._unhandled_input`) |
| Default texture filter | Nearest |
| Renderer | GL Compatibility |
| Pixel snapping | enabled (2d transforms + vertices) |

**Why `canvas_items` not `viewport`:** viewport mode renders text into the 320×180 buffer then NN-scales 6×, turning 7px Cozette into blocky 42px slabs. `canvas_items` scales draw transforms at the native window resolution, so a `font_size = 7` Label rasterizes at actual 42px in a 1920×1080 window. Matches the pygame two-pass render.

**Font (decided 2026-05-23):** **PixelCode** — `assets/fonts/PixelCode.ttf` (regular) and `PixelCode-Bold.ttf`. PixelCode ships real weights so no `FontVariation` embolden trick needed (this was the original plan with Cozette which ships regular-only). Sourced from `C:\Users\andot\Desktop\Pixel Art Fonts\Pixel Code Fonts`.

**Required font import settings** (override Godot's auto-defaults — they set AA on and hinting on, which both kill the pixel look):

| Param | Value |
| --- | --- |
| `antialiasing` | `0` (None) |
| `hinting` | `0` (None) |
| `subpixel_positioning` | `0` (Disabled) |
| `disable_embedded_bitmaps` | `true` |
| `oversampling` | `0.0` (Auto) |

Godot logs `Pixel font detected, disabling subpixel positioning` on import — but it still sets antialiasing=1 and hinting=1 by default. The `.import` files in the repo override these. Don't let the editor re-import without preserving them.

**Theme:** `themes/placeholder_theme.tres` sets `default_font` = PixelCode regular, `default_font_size` = 8, `Button/fonts/font` = PixelCode Bold. Per-Label `theme_override_font_sizes/font_size` overrides for special sizes (PLAY=13, TITLE=14, etc.).

## Mapping pygame → Godot

| Pygame | Godot replacement |
| --- | --- |
| `main.py` event loop | `Main.tscn` + `_process` / `_physics_process` |
| `states/` state machine | Scene-per-state + `SceneManager` AutoLoad |
| `app/context.py` | AutoLoads: `Session`, `Profile`, `Settings` |
| `app/profile.py` JSON in user data dir | `user://profile.json` + server-side mirror |
| `app/display.py` resolution logic | `project.godot` display settings + Settings UI |
| `network/` (whole dir) | Deleted, replaced by [[Networking - Overview]] |
| `player_scripts/player.py` | `Player.tscn` with `CharacterBody2D` |
| `player_scripts/avatar.py` | `Avatar.tscn` resource + image loader |
| `world/level.py` generator | `LevelGenerator.gd` autoload; seed-driven; runs on server, clients reproduce |
| `world/camera.py` | `Camera2D` with smoothing + pixel snap |
| `ui/` widgets | Themed `Control` nodes, packed scenes |
| `ui/metrics_overlay.py` | `DebugHUD.tscn` reading from `Engine.get_frames_per_second()` + peer stats |
| `ui/results_table.py` | `Results.tscn` driven by `match_results` message |
| `tests/` pytest | GUT (Godot Unit Test) addon — install via Asset Library; see `godot/tests/README.md`. First test (determinism of `LevelGenerator`) ships in Phase 4a |

## Scene tree (planned + actual)

The tree below is the eventual target. Items marked ✅ have been scaffolded; the rest are placeholders.

```
res://
├── autoloads/
│   ├── session.gd            ✅ JWT, user_id, current room (empty stub)
│   ├── network_backend.gd    ✅ MultiplayerPeer wrapper (Phase 1 stub)
│   ├── profile.gd            # local profile cache (folded into Settings for now)
│   ├── settings.gd           ✅ display, controls, metrics toggle
│   └── scene_manager.gd      ✅ transitions + back stack + global ESC=back
├── scenes/
│   ├── boot/
│   │   ├── boot.tscn         # load → login
│   │   └── login.tscn
│   ├── main_menu/
│   │   ├── main_menu.tscn    ✅ placeholder boxes/labels at pygame coords
│   │   └── settings.tscn     ✅ placeholder (real form lands Phase 8)
│   ├── avatar/
│   │   └── avatar_editor.tscn  ✅ placeholder (real editor Phase 6)
│   ├── lobby/
│   │   ├── room_browser.tscn   ✅ placeholder (live list Phase 3; cards lead to lobby)
│   │   ├── create_room.tscn    ✅ placeholder (real form + create_room WS Phase 2)
│   │   ├── join_by_code.tscn   ✅ placeholder (real 6-char input + join_room WS Phase 2)
│   │   └── skyward_lobby.tscn  ✅ placeholder (real player sync Phase 2)
│   ├── match/
│   │   ├── match.tscn        # server-authoritative root
│   │   ├── player.tscn
│   │   ├── level.tscn
│   │   └── results.tscn
│   ├── hub/                  # post-MVP
│   │   ├── hub_instance.tscn
│   │   └── avatar.tscn
│   └── debug/
│       └── debug_hud.tscn
├── assets/
│   ├── fonts/cozette_bold.tres
│   ├── sprites/              # imported with Nearest filter
│   └── audio/
└── shared/                   # any plain-data resources
```

## Gameplay sync strategy

Server-authoritative with client prediction:

1. Client samples local input each tick, applies it to local `CharacterBody2D` immediately (prediction).
2. Client sends `push_input(tick, move, jump)` to server (unreliable, ordered).
3. Server runs canonical physics at 30 Hz on its `Player` node.
4. Server's `MultiplayerSynchronizer` pushes `position, velocity, anim_state, alive` to all clients.
5. Client compares server position to its predicted position; if diff > threshold, smoothly reconciles over ~3 frames.

This matches what the pygame original does conceptually (host runs server, but client also runs local physics for responsiveness), just with HLM doing the plumbing.

## Level generation

The pygame generator (`world/level.py`) produces 10 scaled levels from a seed. Port it as `LevelGenerator.gd`:

- Server picks the seed when starting a match, includes it in `match_started`.
- Both server and all clients run the deterministic generator with that seed.
- Server uses generated geometry for physics authority; clients use it for rendering and prediction.
- No level geometry travels over the network — just the seed.

Keeps bandwidth tiny and matches the pygame model.

## Avatar pipeline

Avatars have a model (procedural body + color choices) and a head texture (user-uploaded PNG, cropped to 24×24 or similar).

1. User edits in `avatar_editor.tscn` — local preview, no network until save.
2. On save: `set_avatar` message uploads model JSON + head PNG (base64, ≤ 8 KB).
3. Server stores in Postgres, broadcasts `avatar_updated` to current room.
4. Other clients receive, cache locally by `user_id`, decode PNG into `ImageTexture`.

Replaces the pygame chunked-avatar-transfer protocol with one round trip per avatar change.

## Phased porting order

| Phase | Deliverable | Done = |
| --- | --- | --- |
| 0 | Empty Godot project with locked config | Project opens, pixel test card renders crisp at 1080p |
| 1 | Auth + WS handshake (no rooms yet) | Login form connects, server logs `hello` exchange |
| 2 | Create/join SR private room (no gameplay) | Two clients can see each other in `skyward_lobby.tscn` |
| 3 | Public room browser | Third client can find and join a public room via list |
| 4 | Match start + level gen + free movement | Players can move on the generated level, see each other |
| 5 | Full gameplay parity (orbs, elimination, results) | A 4-player match plays start to finish with results |
| 6 | Avatar editor + persistence | Avatars round-trip through DB and show in lobby/match |
| 7 | Reconnect handling + spectator | Client can drop and rejoin mid-match |
| 8 | Polish: settings, metrics overlay, sound | Feature parity declared |
| 9 | Hub world MVP (see [[Hub World - Design]]) | Walk-around hub with proximity audio |
| 10 | Steam release decision | See [[Open Questions]] |

PDC class deliverable is satisfied at Phase 5 with a writeup of the new architecture.

## What we leave behind (and why)

- `pyinstaller` build system — Godot exports natively
- `scripts/build_exe.ps1` — replaced by Godot export presets
- `dev.bat` multi-window helper — replaced by Godot's `--position` flag for two-window testing
- `tools/scripted_lobby.py` — replaced by a `tests/` GDScript that uses Godot's headless mode
- `tools/list_rooms.py` — replaced by the public room browser itself
- `tools/brochure_performance.py` — keep on pygame side for the CS323 final report; Godot port doesn't need it

## Related

- [[Networking - Overview]]
- [[Networking - Message Contract]]
- [[Hub World - Design]]
- [[Roadmap]]
