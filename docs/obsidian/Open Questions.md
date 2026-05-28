# Open Questions

Things not yet decided. Resolve before they become blockers.

## Product

- [ ] **Final project name.** Using "CSSocialGame" as the working name for now (decided 2026-05-23). Need something brandable before any public-facing release, but no hurry — internal/friend-group builds can stay under the working name.
- [ ] **Rename the game repo** from `pdc_final_project` to something tied to the project name. **Blocked until coursework grade is received** — renaming the repo before grading risks confusing the instructor / breaking submitted links.
- [ ] **Should the hub or Skyward Race be the front door after the hub ships?** Current implementation is login/register → main menu → Play Options. Future question: after Phase 9, should Play default to hub or keep Skyward Race mode selection first?
- [ ] **Text chat in hub?** Proximity voice is the headline feature. Text chat is easy to add but invites moderation work. Probably MVP-skip, post-MVP add as proximity bubbles only (no global chat).

## Identity & accounts

- [ ] **Email verification mandatory or optional at launch?** Mandatory blocks casual try-it-out. Optional lets fake accounts pile up. Probably soft: can log in unverified, can't host rooms until verified.
- [ ] **Display name uniqueness?** Globally unique (Discord-tag-free model — pick one and own it) or duplicates allowed (Discord's discriminator-then-removed model). Leaning unique; 50-user scale makes it easy.
- [ ] **Password reset email flow** — done at Phase 1 or deferred? Probably deferred to Phase 8 polish.

## Networking

- [ ] **Voice/video kill switch for class demos?** A `--no-media` flag to disable LiveKit entirely so demos on weak Wi-Fi don't choke. Probably yes, trivial to add.
- [ ] **Replay/recording of matches?** Would be cool. Not now.
- [ ] **Server tick rate for SR — 30 or 60 Hz?** 30 chosen for bandwidth. Revisit if gameplay feels mushy after Phase 5.

## Levels & environments

(Full design lives in [[Levels & Environments]] — open questions copied here for tracking.)

- [ ] **Difficulty curve shape** — is diff 10 ~10× harder than diff 1, or logarithmic? Needs playtest.
- [ ] **Mid-lobby env switch behavior** — should changing env un-ready everyone? (Lean yes.)
- [ ] **Goal/finish line themed per env?** Likely yes, via `goal_marker` Element with per-env entries.
- [ ] **Difficulty scales tower height or density?** Lean denser; very-tall feels grindy.
- [ ] **LevelData caching** — regenerate from seed each query, or cache per active match? Cache during match for rejoiners; throw away after.

## Hosting

- [ ] **Bump to $12 Droplet pre-emptively?** 2 GB / 1 vCPU. Buys headroom for LiveKit + Postgres without measuring first. Probably wait until we have real numbers from Phase 9.
- [ ] **Backup retention** — how many nightly dumps to keep in the private repo? 30 days seems reasonable. Defer until we see disk usage.
- [ ] **Multi-region?** No. Singapore only. Re-evaluate if a player in EU/NA shows up and complains.

## Steam release (Phase 10)

- [ ] **Pay the $100 Steam Direct deposit?** Recoupable after $1k in sales — unlikely at school-friend scale. Real question is whether Steam discoverability + friends-graph is worth the up-front money.
  - **If yes:** swap `WebSocketMultiplayerPeer` for GodotSteam Multiplayer Peer behind the existing `NetworkBackend` abstraction. Steam Lobbies replace the room browser. Steam Cloud replaces server-side profile mirror. Add achievements.
  - **If no:** stay on itch.io + GitHub Releases. Add Discord invite to the main menu for social discovery.
- [ ] **Even if we don't ship on Steam, use the Steamworks SDK for identity if available?** No — adds dep, requires Steam to be installed, no benefit without the store presence.

## Code & repo discipline

- [x] ~~Single repo or split server out?~~ → **single repo for now** — server lives in `/server` subfolder on `port/godot` branch alongside `/godot`. Decision 2026-05-23. Module path `github.com/CS-StudentGroup/pdc_final_project/server`. Revisit splitting after coursework grade lands; one-line `go.mod` change + import-rewrite when we do.
- [x] ~~Mirror this vault into a `/docs` in one of the repos?~~ → **yes**. Source of truth remains `C:\Users\andot\Documents\CSSocialGame`; repo mirror lives at `docs/obsidian` and includes `.obsidian` for team sync.
- [ ] **GDScript or C# for Godot?** GDScript chosen (fast iteration, native to Godot). Revisit only if a performance hot spot demands it (unlikely at this scope).

## Legal / process

- [ ] **License for the post-school code?** AGPL-3.0 if open-sourced; otherwise all-rights-reserved with friends-only distribution. Defer until Phase 9.
- [ ] **Terms / privacy policy?** Required if any non-school-friend ever signs up. Generator + 1-hour edit pass. Defer until non-school user appears.

## Resolved (for the record)

- ~~Steam vs VPS for backend~~ → **VPS** (see [[Architecture]])
- ~~Mesh vs SFU for media~~ → **LiveKit SFU** (see [[Networking - Proximity Media]])
- ~~UDP/ENet vs WebSocket~~ → **WebSocketMultiplayerPeer** (see [[Networking - Transport & Auth]])
- ~~LAN model vs central rooms~~ → **central server-owned rooms with codes** (see [[Networking - Room Model]])
- ~~Hosting region~~ → **Singapore (DO)** (see [[Infra & Hosting]])
- ~~Backend language~~ → **Go** (see [[Architecture]])
- ~~`canvas_items` vs `viewport` stretch mode~~ → **`canvas_items`** (see [[Skyward Race - Port Plan]])
- ~~Project working name~~ → **CSSocialGame** (placeholder, brandable rename deferred)
- ~~When can we rename `pdc_final_project`~~ → **after the coursework grade is in** — not before
- ~~Window resizability for the Godot client~~ → **resizable + `stretch/aspect="keep"` + `stretch/scale_mode="integer"` + min size = 320×180 + F11/Alt+Enter fullscreen toggle** (industry standard for pixel-art 16:9: Celeste / Stardew / Dead Cells / Hyper Light Drifter all do this combo)
- ~~UI font choice for Godot port~~ → **PixelCode (Regular + Bold)** at `C:\Users\andot\Desktop\Pixel Art Fonts\Pixel Code Fonts`, imported with `antialiasing=0`, `hinting=0`, `subpixel_positioning=0` (Godot's auto-defaults are wrong for pixel fonts and must be overridden)
- ~~Environment count at launch~~ → **2 (Sky + Ice)** — minimum to prove the system; more can ship later
- ~~Lobby env + difficulty UX~~ → **two independent selectors** (host picks env AND a 1–10 difficulty); see [[Levels & Environments]]
- ~~Level architecture~~ → **data-driven Resources + two-layer split** (topology generation is env-agnostic; population is env-aware) — see [[Levels & Environments]]
- ~~Audit fix 1: F11 / ESC handling~~ → **Input Map actions** (`toggle_fullscreen` declared in project.godot; `ui_cancel` built-in for back); no more raw keycode checks
- ~~Audit fix 2: typed element instantiation~~ → **`LevelElement` base class** all elements extend; populator uses typed cast; no duck-typed `"method" in instance` checks
- ~~Audit fix 3: scene refs~~ → **`preload()` PackedScene** for forward navigation in scripts; **`@export_file("*.tscn")` String** for `BackButton.fallback_scene_path` (avoids load cycle); `SceneManager` accepts either
- ~~Audit fix 4: text sizing~~ → **theme type variations** (`Title`, `H1`, `H2`, `BodySmall`, `BodyTiny`, `Primary`, `Secondary`, `Small`, `Tiny`); per-node `font_size` overrides gone
- ~~Audit fix 5: test framework~~ → **GUT addon** (install via Asset Library; instructions in `godot/tests/README.md`); first test = generator determinism in Phase 4a
- ~~Audit fix 6: back-button boilerplate~~ → **reusable `BackButton` scene** at `scenes/ui/back_button.tscn` (handles `go_back` + fallback in one place; `text` overridable for "LEAVE" / "CANCEL")
- ~~Audit fix 7: keyboard/controller focus~~ → `focus_mode = 2` on RoomCard Panels so Tab/`ui_accept` work; Button defaults already FOCUS_ALL
- ~~Audit fix 8: back stack assumption~~ → documented in `scene_manager.gd` (history tracks `scene_file_path` of main scene; revisit if we ever go to a persistent-root model)
- ~~Scene transition style~~ → cloud-wipe prototypes were removed. Keep direct scene changes until a transition fits the final UI art direction.

## Related

- [[Home]]
- [[Roadmap]]
