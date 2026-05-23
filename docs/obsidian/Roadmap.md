# Roadmap

Phased delivery. Each phase ends with something playable or demoable. No "platform" work without a feature riding on it.

## Phase 0 — Bootstrap (1 week)

- [x] Fresh `port/godot` branch on `pdc_final_project` (local-only, user-created 2026-05-23)
- [x] Empty Godot 4.6.2 project in `/godot` with locked pixel config (scaffolded 2026-05-23)
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
- [x] Display name + email uniqueness enforced via DB unique constraints + 409 on conflict (case-insensitive lookups before insert)
- [x] Rate-limit `/auth/*` at 5 burst / ~5 per minute per source IP (token bucket)
- [x] Refresh token rotation — refresh is one-shot; reusing an old refresh fails (theft detection signal)
- [x] No account-enumeration leak on login (same error for "no such user" vs "bad password")
- [x] **User action:** restart server (`go run ./cmd/server` after `go mod tidy`); run the curl smoke test in `server/README.md`

### Phase 1.3 — WebSocket + Godot integration (scaffolded 2026-05-23)

- [x] `server/internal/ws/handler.go` — upgrade `GET /ws?token=<jwt>`, JWT validation in handler, hello envelope sent, read loop logs frames
- [x] `coder/websocket` dependency added
- [x] `server/cmd/server/main.go` — mounts `GET /ws`
- [x] Godot `AuthClient` autoload — async wrappers around `/auth/*` + `/me`, uniform result Dictionary (`success` / `data` / `error` / `status`)
- [x] Godot `NetworkBackend` autoload — real impl using `WebSocketPeer` (NOT `WebSocketMultiplayerPeer` — that's Phase 4 for gameplay HLM). `connect_to_server(jwt)` awaits the hello frame; control message dispatch via `control_message` signal
- [x] Godot `Session.set_from_login(data)` populates user_id/display_name/email/verified/jwt/refresh_token
- [x] Godot `scenes/boot/login.tscn` + `.gd` — email/password form; submit → AuthClient.login → Session → NetworkBackend.connect_to_server → SceneManager.replace(main_menu)
- [x] Godot `scenes/boot/register.tscn` + `.gd` — register form; auto-login after register, same connection flow
- [x] Godot `project.godot` — `AuthClient` added to autoloads; `run/main_scene` → `boot/login.tscn`
- [x] Godot `main_menu.tscn` — `NameLabel` made `unique_name_in_owner`
- [x] Godot `main_menu.gd` — `_ready` shows `Session.display_name` if authenticated
- [x] Server side: hello logged at `INFO`; ws disconnects logged at `INFO`; raw frames logged at `DEBUG`
- [x] Client side: `[NetworkBackend] recv hello` printed; hello payload printed by login/register handlers
- [x] Duplicate active account sessions rejected: a second `GET /ws` for the same `user_id` closes with policy violation reason `account_already_connected`
- [ ] **Deferred:** auto-login on boot (read `user://session.cfg` → refresh_token → /auth/refresh → skip login). Phase 7.
- [ ] **Deferred:** logout button + Session.cfg persistence. Phase 7.
- [ ] **Deferred:** WS keepalive / reconnect on transient drop. Phase 7.
- [ ] **User action:** restart server (`go mod tidy && go run ./cmd/server`); open Godot project; press Play; log in with the kurt/supersecret account from Phase 1.2 smoke test; verify both server log says `ws connected user_id=01KSAM3YJZDR8QEKA3N3QMC2S3` and Godot stdout says `[NetworkBackend] recv hello`

Done = login form connects to deployed server, server logs the user in, client sees hello, main menu shows the user's display name.

## Phase 2 — Private SR room MVP (2 weeks)

- [ ] Room registry (in-memory + Postgres for persistence across restart)
- [ ] `create_room`, `join_room` (private only), `leave_room`
- [ ] 6-char code generator + uniqueness check
- [ ] `skyward_lobby.tscn` scene
- [ ] `lobby_state` push
- [ ] Ready toggle, host promotion on disconnect

Done = two clients can sit in a lobby and see each other.

## Phase 3 — Public room browser (3 days)

- [ ] `visibility` field on rooms
- [ ] `GET /rooms` + WS `subscribe_room_list`
- [ ] `room_browser.tscn` scene
- [ ] Create-room form with public/private toggle

Done = third client can discover a public room without a code.

## Phase 4 — Match start + level gen + free movement (split into 4a/4b/4c)

See [[Levels & Environments]] for the full design driving this split.

### Phase 4a — universal-only baseline (~1 week)

- [ ] Install **GUT** addon (test framework) — see `godot/tests/README.md`
- [ ] First test: generator determinism (same `(env, diff, seed)` → byte-identical `LevelData`)
- [ ] `LevelElement` base class (typed `init_with_seed`)
- [ ] `Element`, `Environment`, `LevelData`, `SlotInfo`, `EnvElementEntry`, `PalettePreset` resource classes
- [ ] `LevelGenerator` (deterministic, band-based topology, seeded RNG only)
- [ ] `LevelPopulator` (data → live scenes; typed cast to `LevelElement`)
- [ ] Single `default.tres` environment with `regular_platform` + `orb` only
- [ ] `Match.tscn` with server-authoritative spawning
- [ ] `Player.tscn` with `CharacterBody2D`
- [ ] Input replication + state replication via `MultiplayerSynchronizer`
- [ ] Client-side prediction with reconciliation
- [ ] `match_started` (with `environment_id` + `seed`) + countdown

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
