# Hub World — Design

The pixel social space players walk around between matches. The "metaverse" framing is intentional but small-scale: this is a chat room with avatars, not a virtual economy.

## Layout

```
+-------------------------------------------------+
|                  HUB INSTANCE                   |
|                                                 |
|    [Bench]       [Fountain]      [Bench]        |
|                                                 |
|       o (me)       o            o               |
|                                                 |
|    [PORTAL]                  [PORTAL]           |
|    Skyward Race              (future game)      |
|                                                 |
|              [Bulletin Board]                   |
|                                                 |
+-------------------------------------------------+
```

Top-down 2D, ~960 × 540 logical hub area, camera follows player. Pixel-art tileset (placeholder Kenney assets initially).

## Instances

| Property | Value |
| --- | --- |
| Max concurrent users per instance | 15 |
| Spawn behavior | Server places into first non-full instance; new instance spun up if all full |
| Idle shutdown | Instance with 0 players for 5 min → killed |
| Persistence | Stateless — instances don't remember anything between spawns |

15-per-instance keeps voice audible (~14 talkers max, ~450 kbps audio per client) and avoids visual chaos.

## Movement

- 4-directional or 8-directional walk (decide once art is in)
- Tile-snap movement disabled — smooth `CharacterBody2D` with arrow/WASD
- Server-authoritative physics at 20 Hz (lighter than SR's 30 Hz; nothing in the hub needs fast input)
- Client prediction same as [[Skyward Race - Port Plan|Skyward Race]]

## Portals

A portal is a `Area2D` trigger that, on overlap + interact key:

1. Calls `enter_portal(portal_id)` on server.
2. Server creates a new `skyward_lobby` room owned by the player, returns its code.
3. Client transitions to the lobby scene with that room joined.

> [!note] Group portal flow
> If multiple players want to portal together, the first one creates a private room, then shares the code in proximity voice. We're not building a "party invite" system in the hub MVP — verbal coordination works at this scale.

## Voice/video

See [[Networking - Proximity Media]] for the full model. In short:

- Audio: everyone in instance, distance-scaled volume
- Video: server-pushed subscription list of nearest ~4, opt-in publish

Mic and camera buttons live in the persistent HUD strip at the bottom of the screen.

## Persistent identity

A user has:

| Field | Source | Editable |
| --- | --- | --- |
| `user_id` | Server-assigned ULID | No |
| `display_name` | User-set at registration | Yes (rate-limited: 1×/day) |
| `avatar_model` | Avatar editor (body color, head shape, etc.) | Yes |
| `avatar_head_png` | User upload, cropped | Yes |

Persisted in Postgres, mirrored to `user://profile.json` for offline rendering.

## Interactions (MVP scope)

| Action | Input | Effect |
| --- | --- | --- |
| Walk | WASD/arrows | Move avatar |
| Toggle mic | M | Mute/unmute |
| Toggle camera | V | Start/stop video publish |
| Interact | E | Trigger nearest interactable (portal, sign) |
| Open menu | Esc | Settings, profile, leave hub |
| Wave/emote | Q (with picker) | Plays animation visible to nearby peers — post-MVP |
| Chat (text) | Enter | Local proximity bubble — post-MVP |

## Bulletin board (post-MVP)

A non-MVP feature worth scoping early so we don't paint ourselves into a corner:

- Static board sprite players can stand in front of and read
- Server-side editable by admin (just the user themselves, initially)
- Use case: announce events, post Discord link, share match codes

## What's explicitly out of scope for hub MVP

- Multiple hub maps / themed instances
- Furniture placement / decoration
- Inventory / items
- Persistent player position (always spawn at fixed point)
- Friend lists / parties
- Server-side chat history (proximity bubbles are ephemeral)
- Mobile support

## Related

- [[Networking - Proximity Media]]
- [[Networking - Message Contract]]
- [[Skyward Race - Port Plan]]
- [[Vision]]
