# Roadmap

Phased delivery. Each phase ends with something playable or demoable. No "platform" work without a feature riding on it.

## Phase 0 — Bootstrap (1 week)

- [x] Fresh `port/godot` branch on `pdc_final_project` (local-only, user-created 2026-05-23)
- [x] Empty Godot 4.6.2 project in `/godot` with locked pixel config (scaffolded 2026-05-23; audit fix explicitly sets `stretch/aspect="keep"` and `window/size/resizable=true`)
- [x] Main menu screen ported with placeholder boxes/labels (no sprites yet) — earlier than originally planned, in place of the "pixel test card" which would have been thrown away
- [x] AutoLoad skeletons for `SceneManager`, `Session`, `Settings`, `NetworkBackend` (Network is a stub)
- [x] Placeholder Theme resource so all Buttons/Panels render as visible boxes without sprites
- [x] PixelCode font imported with pixel-perfect params + applied as theme default
- [x] Window-resizability nailed (resizable + keep aspect + integer scale + 320×180 min + F11 toggle)
- [x] Placeholder destination scenes scaffolded so MainMenu buttons go somewhere:
      `settings`, `avatar_editor`, `room_browser`, `create_room`, `join_by_code`, `skyward_lobby`
- [x] `SceneManager` upgraded with back-stack + global `ui_cancel` = back
- [x] Audit pass: Input Map actions (replaces raw keycodes), theme type variations (replaces per-node font_size overrides), reusable `BackButton` scene, focusable RoomCards, `PackedScene` preloads in scripts (replaces path strings), `tests/` folder + GUT install docs
- [ ] Open the project in Godot 4.6.2 and confirm the menu + every destination renders + every BACK works
- [ ] Install GUT addon via Asset Library (deferred to Phase 4a — see `godot/tests/README.md`)
- [ ] New repo `cssocialgame-server` initialized
- [ ] Hello-world Go server with `/health` endpoint
- [ ] Docker-compose with go-server + postgres locally
- [ ] This vault committed (or mirrored) into a `/docs` somewhere

Done = both projects open, repo discipline established, no code written yet that we'll throw away.

> [!note] Scaffold notes (2026-05-23)
> - Project starts directly at `scenes/main_menu/main_menu.tscn`. A boot/login scene will land in Phase 1 and the main scene will be re-pointed at that.
> - Main menu mirrors the pygame `MENU_ASSET_RECTS` coordinates exactly (320×180 logical) so sprites authored at those rects drop in without re-positioning.
> - Only EXIT is wired. PLAY / SETTINGS / AVATAR log placeholder messages pointing at their delivery phase.
> - The `placeholder_theme.tres` will be replaced/extended once Cozette + sprites arrive. Theme replacement should not require touching scene files.

## Phase 1 — Auth + WS (split into 1.1 / 1.2 / 1.3)

### Phase 1.1 — Server bootstrap (scaffolded 2026-05-23)

- [x] `/server` folder in `pdc_final_project` (same repo as `/godot`); module path `github.com/CS-StudentGroup/pdc_final_project/server`
- [x] `cmd/server/main.go` with stdlib `net/http` + Go 1.22 ServeMux patterns
- [x] `internal/config` — env-driven config with validation
- [x] `internal/db` — pgx pool, sized for $6 box (MaxConns=10)
- [x] `internal/httpx` — RequestID, AccessLog (slog), panic Recover middleware
- [x] `internal/db/migrations/001_init.sql` — `users` + `refresh_tokens` tables, indexes, `touch_updated_at` trigger
- [x] `docker-compose.yml` — Postgres only; server runs on host for fast iteration
- [x] `.env.example`, `.gitignore`, README with setup steps
- [x] `GET /health` endpoint that pings DB
- [x] **User action:** install Go 1.23+, start Docker Desktop, `docker-compose up -d && go mod tidy && go run ./cmd/server`, verify `curl localhost:8080/health` returns `ok`

### Phase 1.2 — Auth endpoints (scaffolded 2026-05-23)

- [x] `internal/auth/password.go` — bcrypt cost-12 wrapper
- [x] `internal/auth/jwt.go` — HS256 mint + verify (15min access); random+sha256 refresh tokens (30d, NOT JWT)
- [x] `internal/auth/store.go` — pgx queries; `RotateRefreshToken` is a tx (revoke old + insert new atomically)
- [x] `internal/auth/handlers.go` — `POST /auth/register|verify|login|refresh|logout`, `GET /me`
- [x] `internal/auth/middleware.go` — Bearer JWT verifier middleware + per-IP token bucket rate limiter
- [x] `internal/auth/errors.go` — typed `*auth.Error` with stable codes + HTTP status mapping; standard JSON error envelope
- [x] Email verification: stub send (log token) for Phase 1; real Gmail SMTP later
- [x] Display name + email uniqueness enforced via DB unique constraints + 409 on conflict (case-insensitive lookup probes before insert; case-insensitive unique indexes are the race-safe source of truth)
- [x] Rate-limit `/auth/*` at 5 burst / ~5 per minute per source IP (token bucket; `X-Forwarded-For` trusted only from configured proxy CIDRs)
- [x] Refresh token rotation — refresh is one-shot; reusing an old refresh fails (theft detection signal)
- [x] No account-enumeration leak on login (same error for "no such user" vs "bad password")
- [x] **User action:** restart server (`go run ./cmd/server` after `go mod tidy`); run the curl smoke test in `server/README.md`

### Phase 1.3 — WebSocket + Godot integration (scaffolded 2026-05-23)

- [x] `server/internal/ws/handler.go` — upgrade `GET /ws?token=<jwt>`, JWT validation in handler, origin verification enabled, hello envelope sent, read loop logs frames
- [x] `coder/websocket` dependency added
- [x] `server/cmd/server/main.go` — mounts `GET /ws`
- [x] Godot `AuthClient` autoload — async wrappers around `/auth/*` + `/me`, uniform result Dictionary (`success` / `data` / `error` / `status`)
- [x] Godot `NetworkBackend` autoload — real impl using `WebSocketPeer` (NOT `WebSocketMultiplayerPeer` — that's Phase 4 for gameplay HLM). `connect_to_server(jwt)` awaits the hello frame; control message dispatch via `control_message` signal; request/reply helper tracks envelope `id`
- [x] Godot `Session.set_from_login(data)` populates user_id/display_name/email/verified/jwt/refresh_token
- [x] Godot `scenes/boot/login.tscn` + `.gd` — email/password form; submit → AuthClient.login → Session → NetworkBackend.connect_to_server → SceneManager.replace(main_menu)
- [x] Godot `scenes/boot/register.tscn` + `.gd` — register form; auto-login after register, same connection flow
- [x] Godot `project.godot` — `AuthClient` added to autoloads; `run/main_scene` → `boot/login.tscn`
- [x] Godot `main_menu.tscn` — `NameLabel` made `unique_name_in_owner`
- [x] Godot `main_menu.gd` — `_ready` shows `Session.display_name` if authenticated
- [x] Server side: hello logged at `INFO`; ws disconnects logged at `INFO`; raw frames logged at `DEBUG`
- [x] Client side: `[NetworkBackend] recv hello` printed; hello payload printed by login/register handlers
- [x] Duplicate active account sessions rejected: a second `GET /ws` for the same `user_id` closes with policy violation reason `account_already_connected`
- [x] Active WS connections tracked and closed on server shutdown before `http.Server.Shutdown`
- [x] Login/register submit paths guard against double-submit while an async request is in flight
- [x] Phase 1 lobby placeholders no longer enter `skyward_lobby` without a real server room
- [ ] **Deferred:** auto-login on boot (read `user://session.cfg` → refresh_token → /auth/refresh → skip login). Phase 7.
- [ ] **Deferred:** logout button + Session.cfg persistence. Phase 7.
- [ ] **Deferred:** WS keepalive / reconnect on transient drop. Phase 7.
- [ ] **User action:** restart server (`go mod tidy && go run ./cmd/server`); open Godot project; press Play; log in with the kurt/supersecret account from Phase 1.2 smoke test; verify both server log says `ws connected user_id=01KSAM3YJZDR8QEKA3N3QMC2S3` and Godot stdout says `[NetworkBackend] recv hello`

Done = login form connects to deployed server, server logs the user in, client sees hello, main menu shows the user's display name.

## Phase 2 — Private SR room MVP (implemented 2026-05-24)

- [x] Room registry in `/server/internal/rooms` (in-memory active state; room tables scaffolded for persistence/reconnect follow-up)
- [x] `create_room`, `join_room` (private only), `leave_room`
- [x] 6-char code generator + uniqueness check
- [x] `skyward_lobby.tscn` scene wired to server snapshots
- [x] `lobby_state` push
- [x] Ready toggle, host promotion on disconnect

Done = two clients can sit in a lobby and see each other.

## Phase 3 — Public room browser (scaffolded 2026-05-23)

- [x] `visibility = "public"` accepted by `create_room` (Phase 2's "private only" guard dropped)
- [x] WS `subscribe_room_list` / `unsubscribe_room_list` messages; subscribers tracked per-Registry
- [x] `room_list_update` push payload `{rooms: [{code, name, players, capacity, level, environment_id, state}]}` — sorted by code for stable client ordering
- [x] Server fans out `room_list_update` after every create / join / leave (set_ready and host_changed skipped — those don't change browser-visible fields)
- [x] `UnregisterClient` cleans up subscriber set on WS disconnect
- [x] `BrowserEntry` struct kept minimal (no host_user_id, no players[], etc.) — browser only needs enough to decide which room to join
- [x] `room_card.tscn` + `.gd` — reusable, focusable Panel; emits `pressed(code)` on click or `ui_accept`
- [x] `room_browser.tscn` rebuilt — ScrollContainer + VBoxContainer for dynamic cards, StatusLabel for transient messages, EmptyLabel when list is empty
- [x] `room_browser.gd` — subscribes on `_ready`, unsubscribes on `_exit_tree`, renders cards from `room_list_update`, click → `join_room` → lobby
- [x] `create_room.tscn` rebuilt — real `NameField` (LineEdit), `LevelSpinBox` (1-10), `VisibilityToggle` (CheckButton with label flip Private↔Public), `StatusLabel`
- [x] `create_room.gd` — reads form values, sends real `create_room`; "private" is the default toggle state per vault decision
- [x] HTTP `GET /rooms` endpoint **deferred** — WS push is the primary path. Add only if a non-Godot client needs it.
- [x] Per-subscriber rate limit (1/s spec'd in [[Networking - Room Model]]) **deferred** — at our scale, no abuse risk yet
- [x] **User action:** restart server (`go run ./cmd/server`); open two Godot clients; in client A, CREATE a public room; in client B, open BROWSE ROOMS and confirm the room appears live; click it to join

Done = third client can discover a public room without a code.

## Phase 4 — Match start + level gen + free movement (split into 4a/4b/4c)

See [[Levels & Environments]] for the full design driving this split.

### Phase 4a — universal-only baseline (split into 4a.1 / 4a.2 / 4a.3)

#### Phase 4a.1 — Generator + populator foundation (scaffolded 2026-05-24)

- [x] `LevelElement` base class (Node2D, typed `init_with_seed`); every element scene root extends it. LevelPopulator casts with `as LevelElement` — type mismatch fails loudly.
- [x] Resource classes: `Element` (with Category enum), `LevelEnvironment` (renamed from `Environment` — Godot's built-in shadowed), `EnvElementEntry`, `PalettePreset`, `SlotInfo`, `LevelData`. All in `godot/world/`.
- [x] `LevelGenerator` (RefCounted, static `generate(env, difficulty, seed) → LevelData`). Band-based topology (50px bands). Platform count thins out at higher difficulty. Universal weighted picker from env's `element_set`, filtered by category + difficulty. Pure deterministic — only the seeded `RandomNumberGenerator`, no `randi()` / wall clock.
- [x] `LevelPopulator` (Node, `populate(data, parent) → int`). Walks slots, looks up element from env's element_set, typed instantiate, parents.
- [x] `EnvironmentRegistry` autoload (autoload name: `Environments`) — discovers every `.tres` LevelEnvironment under `res://resources/environments/` at boot.
- [x] Element scenes: `regular_platform` (50×8 drawn rect with shade), `orb` (small circle with highlight). Both extend `LevelElement`. No assets needed — pure `_draw`.
- [x] Resource files: `resources/elements/{regular_platform,orb}.tres`, `resources/palettes/default.tres`, `resources/environments/default.tres` (universal-only baseline).
- [x] `Match.tscn` + `match.gd` — standalone (F6 in editor) generates and renders a tower with hardcoded test params (env=default, diff=1, seed=42). Reads `Session.match_params` if a server `match_started` populated them. Arrow keys scroll Camera2D through the tower. DebugLabel at top shows current params + slot count.
- [x] `Session.match_params` field — carrier for server's `match_started` payload (env_id, level, seed, etc.).
- [x] `project.godot` — `Environments` autoload registered after `NetworkBackend`.
- [x] **User action:** open Godot, navigate to `scenes/match/match.tscn`, hit F6 — should render a tower of platforms and orbs. Change `DEFAULT_SEED` in `match.gd` and re-run to see deterministic variation.
- [ ] **Deferred to 4a.2:** server `start_match` handler + `match_started` broadcast, lobby START wiring, Session-driven match transition
- [ ] **Deferred to 4a.3:** Player.tscn (CharacterBody2D), `WebSocketMultiplayerPeer` (HLM), MultiplayerSpawner, MultiplayerSynchronizer for player state, client-side prediction + reconciliation
- [ ] **Deferred (GUT setup):** install via Asset Library, first test = generator determinism (same `(env, diff, seed)` → byte-identical `LevelData`)

Done = the generator visibly produces tower geometry; F6 on Match.tscn renders it; varying the seed varies the level deterministically.

#### Phase 4a.2 — Lobby → Match flow (scaffolded 2026-05-24)

- [x] Server `start_match` handler in `internal/rooms/registry.go` — validates host, validates all non-host players ready, refuses if room state isn't `waiting`, transitions `Waiting → InMatch`
- [x] `StateInMatch = "in_match"` constant added; browser entries reflect the state change via the `room_list_update` re-broadcast
- [x] Per-recipient `match_started` payload `{level, environment_id, seed, start_at_server_ts, your_player_id, room_id}` — each player gets their own `your_player_id` baked in
- [x] Match seed via `crypto/rand` (positive int63, falls back to `time.Now().UnixNano()` only if rand fails)
- [x] 1.5 s countdown via `start_at_server_ts = now + 1500ms` (clients can render a "starting in N..." overlay if they want; Match scene currently just renders immediately — countdown UX lands when player physics does)
- [x] `start_match_ok` reply only sent when caller used `send_control_request` (optional ack)
- [x] Lobby `_on_start_pressed` — guards (busy / disconnected / not host), sends `start_match`, surfaces error reply messages from the server
- [x] Lobby `_on_control_message` — dispatches `match_started`, populates `Session.match_params`, `SceneManager.replace(MATCH_SCENE)`
- [x] `MATCH_SCENE` preloaded at top of `skyward_lobby.gd` (no cycle — match.gd doesn't preload lobby)
- [x] `Match.gd` unchanged — already reads `Session.match_params` from Phase 4a.1
- [ ] **User action:** restart server; in client A, log in and CREATE a room; in client B, JOIN BY CODE and READY; back in A, START → both clients should transition into the same procedurally-generated level (same seed → same layout). Each client's DebugLabel shows the same `seed=...`.

Done = host clicks START → server-generated level renders on every player's screen identically.

#### Phase 4a.3 — Player physics + solo gameplay (scaffolded 2026-05-24)

Originally bundled with HLM multiplayer sync; split into 4a.3 (this — solo) and a new **4a.4** (multiplayer) so the physics + collision foundation is testable in isolation before the multiplayer architecture decision lands.

- [x] `MatchPlayer extends CharacterBody2D` at `scenes/match/player.gd` — `_physics_process` with gravity, horizontal input via `Input.get_axis`, `is_action_just_pressed("jump")` + `is_on_floor()` guard
- [x] `Player.tscn` — `CharacterBody2D` root + `CollisionShape2D` (8×12 RectangleShape2D); `_draw` placeholder body until art lands
- [x] Tuning: `SPEED=110`, `JUMP_VELOCITY=-210`, `GRAVITY=480` — chosen so one jump clears `BAND_HEIGHT=50` with margin
- [x] `regular_platform.tscn` now has `StaticBody2D` + `CollisionShape2D` (50×8); `one_way_collision = true` so the tower-jump-through-from-below pattern works
- [x] `match.gd` — `_spawn_player` instantiates Player at `(160, total_height - 25)`, `_add_floor` adds a code-generated StaticBody2D floor under the level so the player has something to land on at spawn time
- [x] Camera now follows player vertically via `lerpf(0.15)` smoothing with clamp at level top/bottom; replaces the arrow-key scroll from 4a.1
- [x] Input Map actions in `project.godot` — `move_left` (A + Left), `move_right` (D + Right), `jump` (Space + Up + W)
- [x] **User action:** F6 on `scenes/match/match.tscn` — player spawns at bottom, can run left/right with WASD/arrows, jump with Space/W/Up, land on platforms (and pass UP through them from below). Climb the tower to verify the generator's reachability across bands.
- [ ] **Deferred to 4a.4:** multi-player position sync, win condition (reaching the top), orb pickup collision

Done = a single client can climb the generated tower end-to-end. Reachability of platforms validates the generator's spacing tuning.

#### Phase 4a.4 — Multiplayer sync (next turn)

> [!info] Architecture decision pending
> Vault contract originally specified Godot HLM (WebSocketMultiplayerPeer + MultiplayerSynchronizer). At implementation time this needs to be re-evaluated against the actual reality of running a Go backend (not Godot) as authority. Three options under consideration:
> - **A.** Client-authoritative position relay over the existing control WS — cheapest, weak anti-cheat, fine for friend group
> - **B.** Server-authoritative without Godot HLM — Go reimplements physics, clients predict + reconcile (the "real" multiplayer pattern; more work)
> - **C.** Godot HLM with one player elected as host — host runs simulation, others are pure clients; would require either WebSocketMultiplayerPeer routing through Go OR a separate peer-to-peer connection
>
> Lean toward **A** for Phase 4a.4 (school-friend audience, MVP), with the architectural seam abstracted so we can upgrade to B later if cheating becomes a problem. Lock the decision at the start of 4a.4.

- [ ] Position broadcast protocol (likely C→S `player_state` at 20 Hz, S→C `peer_state_update` fanout to others in the match)
- [ ] Server-side per-match player position tracking (in `internal/rooms` or new `internal/match` package)
- [ ] Client sends position updates while in Match scene
- [ ] Remote player rendering — Match scene tracks `peers: Dictionary[user_id, MatchPlayer]`, applies received positions with interpolation
- [ ] Match cleanup on player disconnect / leave

Done = players can move on a generated level and see each other smoothly; no env selector yet.

### Phase 4b — environment system (~3–4 days)

- [ ] `EnvironmentRegistry` autoload — discovers `resources/environments/*.tres`
- [ ] Sky and Ice `Environment` resources + backgrounds + palettes + music
- [ ] Sky-exclusive: `cloud_platform`, `wind_gust`
- [ ] Ice baseline: ice-textured `regular_platform` variant
- [ ] Env selector carousel in `skyward_lobby.tscn`; host-only
- [ ] Env icon on `room_browser.tscn` cards
- [ ] `set_environment` WS message + server validation
- [ ] `match_started` env_id flows through to populator

Done = host can pick Sky or Ice; lobbies and matches render with the chosen env.

### Phase 4c — stateful + exclusive elements (~1 week)

- [ ] `StatefulElement` base script (server-owned state + sync to clients)
- [ ] `fragile_ice_platform` (Ice exclusive)
- [ ] `slippery_platform` (Ice exclusive)
- [ ] `icicle_drop` (Ice exclusive)
- [ ] `spike_strip` (universal hazard)
- [ ] `moving_platform` (universal, diff ≥ 3)
- [ ] `spring` (universal, diff ≥ 4)
- [ ] `MultiplayerSynchronizer` config per stateful element

Done = Ice levels actually feel different to play, not just look different.

## Phase 5 — Gameplay parity (2 weeks)

- [ ] Orb collection
- [ ] Elimination
- [ ] Win condition
- [ ] `match_results` + results scene
- [ ] Rematch flow
- [ ] Spectator after elimination

Done = 4-player match plays start to finish.

**CS323 deliverable satisfied here.** Writeup of new architecture vs pygame can be drafted.

## Phase 6 — Avatar editor + persistence (1 week)

- [ ] `avatar_editor.tscn` (model picker + image crop)
- [ ] `set_avatar` round-trip
- [ ] Avatar cache on client by `user_id`
- [ ] Render avatars in lobby + match
- [ ] Postgres `avatars` table

Done = your avatar follows you across sessions and devices.

## Phase 7 — Reconnect handling (3 days)

- [ ] Session re-attach on WS reconnect within 30 s
- [ ] Snapshot replay on rejoin
- [ ] Client-side reconnect UI (toast + retries)

Done = network blip doesn't drop you from a match.

## Phase 8 — Polish (1 week)

- [ ] Settings screen (display, controls, metrics)
- [ ] Debug HUD with FPS/RTT/loss
- [ ] Sound effects (ported from pygame)
- [ ] Music
- [ ] Keybind remapping

Done = standalone game release candidate.

## Phase 9 — Hub world MVP (3–4 weeks)

- [ ] `HubInstance` scene + spawning logic
- [ ] Walk + interact
- [ ] Portal triggers → SR lobby create
- [ ] Avatar nodes in hub (reuse avatar pipeline)
- [ ] LiveKit integration (token mint server-side, client connect)
- [ ] Proximity volume curve
- [ ] Server-driven video subscription
- [ ] Mic/camera toggles in HUD

Done = walk around with friends, talk to nearby ones, walk into a portal to race.

## Phase 10 — Steam decision (post Phase 9)

See [[Open Questions]]. Decide based on audience growth and willingness to pay $100 Steam Direct deposit.

## Slip protection

- Each phase has a "done =" clause. If we slip, we cut scope **within the phase**, not skip to a later phase out of order.
- Hub world (Phase 9) is the most likely thing to balloon. If voice/video integration takes more than a week, ship hub-without-voice first.
- Phases 2–5 are the CS323 critical path. Everything else can slip without affecting the academic deliverable.

## Related

- [[Vision]]
- [[Skyward Race - Port Plan]]
- [[Hub World - Design]]
- [[Open Questions]]
