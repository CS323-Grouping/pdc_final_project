# CSSocialGame — Godot client

Godot 4.6 port of the Skyward Race pygame original. Working name is **CSSocialGame**; the in-world game keeps the name **Skyward Race**.

> Full plan lives in `../docs/obsidian` — start at `Home.md`. This README only covers how to open and what's here.

## Open

```powershell
& "C:\Users\andot\Desktop\PinnedApps\Godot_v4.6.2-stable_win64.exe" --path godot
```

First open will let the editor generate `.godot/` cache and `.uid` files for new resources. Commit the resulting `*.import` and `*.uid` files alongside the source.

## Locked-in pixel config

(See vault: `Skyward Race - Port Plan.md`)

- Internal resolution: **320×180**
- Stretch mode: **canvas_items** (NOT viewport)
- Scale mode: **integer**
- Default texture filter: **Nearest**
- Renderer: **GL Compatibility**
- Pixel snapping enabled

Author assets at the 320×180 scale and place nodes at those coordinates. Godot scales the frame to the window automatically — no manual scaling code.

## Structure

```
godot/
├── project.godot          # locked-in display + autoload config
├── icon.svg               # placeholder icon
├── autoloads/             # AutoLoad singletons
│   ├── scene_manager.gd   # SceneManager — switch scenes
│   ├── session.gd         # Session — JWT, user_id, current room (empty stub)
│   ├── settings.gd        # Settings — display/controls, persisted to user://
│   ├── auth_client.gd     # AuthClient — async HTTP wrappers for /auth/* + /me
│   └── network_backend.gd # NetworkBackend — control WebSocket + request/reply helper
├── scenes/
│   ├── boot/              # login/register
│   ├── main_menu/         # main menu — placeholder boxes + labels
│   ├── avatar/            # placeholder editor
│   ├── lobby/             # placeholder browser/create/join/lobby scenes
│   └── ui/                # reusable controls
├── themes/
│   └── placeholder_theme.tres  # flat-color Buttons + Panels for the box look
└── assets/
    ├── fonts/    # (empty — Cozette goes here later)
    ├── sprites/  # (empty — author at 320×180 scale, drop in here)
    └── audio/    # (empty)
```

## Wired so far

- Boot scene is `scenes/boot/login.tscn`
- Register/login call the Go auth API, then open the control WebSocket and wait for `hello`
- Control WS requests use envelope ids through `NetworkBackend.send_control_request`
- Create/join room screens now call `create_room` / `join_room`; lobby consumes `lobby_state` and sends `set_ready`
- Main menu shows the authenticated display name after login
- Placeholder destination scenes exist for avatar, settings, room browser, create, join, and lobby

## What's NOT here yet

- Real room create/join/list messages (Phase 2–3)
- Match scenes (Phase 4–5)
- Real avatar editor persistence (Phase 6)
- Final sprites/audio
- Settings dialog, name-edit dialog (Phase 8)

See vault `Roadmap.md` for the full phased plan.
