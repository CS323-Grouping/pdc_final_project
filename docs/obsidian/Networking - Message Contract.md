# Networking — Message Contract

The wire shape between the Godot client and the Go backend. Two layers:

1. **Control messages** — explicit request/response or push, JSON over WS.
2. **HLM traffic** — Godot's `MultiplayerSynchronizer` + RPCs, framed by the engine.

> [!note] Why two layers
> Godot HLM is fantastic for "this Node's properties are replicated" and "call this method on the authority." It's awkward for auth handshakes, room browsing, and account management. So control messages ride alongside HLM on the same WS, distinguished by frame type.

## Frame envelope

Every WS frame is JSON with this shape:

```json
{
  "t": "msg_type",        // string discriminator
  "id": "01HXYZ...",      // optional client-set correlation id for replies
  "d": { /* payload */ }
}
```

Server replies set `id` matching the request. Push messages have no `id`.
Godot's `NetworkBackend.send_control_request(t, d)` generates the request id,
waits for the matching reply, and normalizes `err` replies into
`{success=false, error={code,message}}`.

Godot HLM frames are passed through transparently by `WebSocketMultiplayerPeer` — they don't use this envelope.

## Control message catalog

### Auth (HTTP, not WS)

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/auth/register` | `{email, password, display_name}` | `{user_id}` + verification email |
| POST | `/auth/verify` | `{token}` | 204 |
| POST | `/auth/login` | `{email, password}` | `{access_token, access_expires_at, refresh_token, refresh_expires_at, user}` |
| POST | `/auth/refresh` | `{refresh_token}` | `{access_token, access_expires_at, refresh_token, refresh_expires_at, user}` |
| POST | `/auth/logout` | `{refresh_token}` | 204 |
| GET | `/me` | Bearer access token | `{id, email, display_name, verified, created_at}` |

### On WS open

```
S→C  hello { server_version, your_user_id, your_display_name }
```

### Room lifecycle

| Type | Direction | Payload | Notes |
| --- | --- | --- | --- |
| `create_room` | C→S | `{type, name, visibility, level, environment_id, capacity}` | SR only; `environment_id` see [[Levels & Environments]] |
| `room_created` | S→C | `{code, room_id, snapshot}` | reply; snapshot includes `environment_id` |
| `join_room` | C→S | `{code}` | |
| `join_ok` | S→C | `{room_id, your_player_id, snapshot}` | reply |
| `join_err` | S→C | `{reason}` | reply; reason ∈ {not_found, full, in_progress, banned} |
| `leave_room` | C→S | `{}` | always succeeds |
| `leave_ok` | S→C | `{}` | reply |
| `enter_hub` | C→S | `{}` | |
| `hub_assigned` | S→C | `{instance_id, snapshot}` | |
| `kick_player` | C→S | `{target_player_id}` | host only |
| `host_changed` | S→C (push) | `{new_host_player_id}` | |

### Room browser (SR public rooms)

| Type | Direction | Payload |
| --- | --- | --- |
| `subscribe_room_list` | C→S | `{}` |
| `unsubscribe_room_list` | C→S | `{}` |
| `room_list_update` | S→C (push) | `{rooms: [...]}` |

### Lobby (SR)

| Type | Direction | Payload |
| --- | --- | --- |
| `set_ready` | C→S | `{ready: bool}` |
| `ready_ok` | S→C | `{ready: bool}` |
| `set_level` | C→S | `{level: int}` | host only; 1–10 |
| `set_environment` | C→S | `{environment_id: string}` | host only; server validates against `EnvironmentRegistry`; resets readies |
| `set_room_name` | C→S | `{name: string}` | host only |
| `set_visibility` | C→S | `{visibility}` | host only |
| `start_match` | C→S | `{}` | host only; requires all ready |
| `lobby_state` | S→C (push) | `{room_id, code, players, ready_set, host_user_id, level, environment_id, state, capacity}` |

### Match (SR) — control only; gameplay sync uses HLM

| Type | Direction | Payload |
| --- | --- | --- |
| `match_started` | S→C | `{level, environment_id, seed, start_at_server_ts, your_player_id}` | clients run `LevelGenerator.generate(env, level, seed)` to reproduce geometry — see [[Levels & Environments]] |
| `match_results` | S→C | `{placements: [...]}` |
| `request_rematch` | C→S | `{}` |

### Avatar

| Type | Direction | Payload | Notes |
| --- | --- | --- | --- |
| `set_avatar` | C→S | `{model: {...}, head_png_b64}` | head ≤ 8 KB |
| `avatar_updated` | S→C (push) | `{user_id, model, head_png_b64}` | broadcast to roommates |

### Errors

```
S→C  err { code, message, ref_id }    // ref_id matches the request id if any
```

## HLM contract (gameplay)

### Skyward Race match scene

Server (authority) spawns a `Match` scene with one `Player` child per participant.

```gdscript
# Match.gd — authority on server, replicated to clients
extends Node
@export var seed: int
@export var level_index: int

@rpc("authority", "call_local", "reliable")
func start_countdown(server_ts_ms: int): pass

@rpc("authority", "call_local", "reliable")
func reveal_results(placements: Array): pass
```

```gdscript
# Player.gd — authority on the owning client for input, server for physics
extends CharacterBody2D
@export var owner_user_id: String

# input replicated client → server
@rpc("any_peer", "call_local", "unreliable_ordered")
func push_input(tick: int, move: int, jump: bool): pass

# state replicated server → all clients via MultiplayerSynchronizer
# (position, velocity, anim_state, alive)
```

A `MultiplayerSynchronizer` config on `Player` replicates: `position`, `velocity`, `anim_state`, `alive` from server → clients at 30 Hz with delta compression.

### Hub world scene

Server runs a `HubInstance` scene per instance. Each player is an `Avatar` node.

```gdscript
# Avatar.gd
extends CharacterBody2D
@export var owner_user_id: String
@export var display_name: String
@export var avatar_model_id: String

# input replicated client → server
@rpc("any_peer", "call_local", "unreliable_ordered")
func push_input(tick: int, move_vec: Vector2, interact: bool): pass

# server pushes:
#   position, facing, anim_state at 20 Hz via MultiplayerSynchronizer
```

Synchronizer interest management: clients only receive sync packets for avatars within ~400 px of their own. Saves bandwidth when an instance is full.

### Voice/video subscription control (out-of-band, see [[Networking - Proximity Media]])

```
S→C (push)  livekit_update {
    token: "...",                 // LiveKit join token
    subscribe: ["user_a", "user_b", ...],  // who to subscribe video from
    unsubscribe: ["user_c"]
}
```

Audio is universal within instance (cheap, ~14 tracks max). Video sub list is server-decided based on proximity.

## Cross-language type sharing

| Approach | Cost | Choice |
| --- | --- | --- |
| Hand-mirror Go structs in GDScript | Drift risk, easy | **Pick** initially |
| Codegen from a shared schema (protobuf / JSON Schema) | Setup overhead | Defer until drift bites |
| Hand-edited spec doc as source of truth | This note | Yes, this is it |

This file is the spec. When it changes, both sides update.

## Versioning

```
hello.server_version = "0.3.0"
```

Client compares against its build version. Mismatch on `major.minor` → soft block ("please update"), `patch` mismatch → warn only.

## Related

- [[Networking - Transport & Auth]]
- [[Networking - Room Model]]
- [[Networking - Proximity Media]]
- [[Skyward Race - Port Plan]]
