# Home

Living plan for the redesigned **Skyward Race** + **Pixel Social Hub**. Two products in one Godot binary, one Go backend on a $6 VPS.

> [!info] Status as of 2026-05-23
> Pygame original (`main` branch on `pdc_final_project`) is the reference. Godot port has not started yet on the working tree (`port/godot` branch was deleted to restart clean). All plans below are pre-implementation.

## Quick links

- [[Vision]] — what we're actually building and for whom
- [[Architecture]] — system topology, repo layout, decided stack
- [[Networking - Overview]] — entry point for the whole network story
- [[Skyward Race - Port Plan]] — what changes vs the pygame original
- [[Levels & Environments]] — procedural level system + themed environments (Sky, Ice)
- [[Hub World - Design]] — the social/proximity world
- [[Infra & Hosting]] — the single VPS, services, costs
- [[Roadmap]] — phased delivery
- [[Open Questions]] — decisions not yet made

## Network sub-notes

- [[Networking - Transport & Auth]] — WebSocketMultiplayerPeer + JWT
- [[Networking - Room Model]] — public/private rooms, room codes
- [[Networking - Message Contract]] — Godot ↔ Go wire shape
- [[Networking - Proximity Media]] — LiveKit voice/video

## Decisions snapshot

| Topic | Choice | Note |
| --- | --- | --- |
| Client engine | Godot 4.6.2 | Pixel config locked, see [[Skyward Race - Port Plan]] |
| Backend language | Go (stdlib + sqlc + pgx) | Single binary serves both products |
| Transport | `WebSocketMultiplayerPeer` over WSS:443 | No raw UDP, no NAT pain |
| Auth | Self-rolled bcrypt + JWT | No Steam ticket (yet) |
| Hosting | DigitalOcean $6/mo Singapore | LiveKit + Postgres + Caddy + Go on same box |
| Voice/video | LiveKit self-hosted SFU | Proximity-driven subscriptions |
| Distribution | itch.io + GitHub Releases | Steam deferred ($100 deposit not justified yet) |
| Multiplayer | Server-authoritative, no client hosts | Drops LAN broadcast + listen-server code entirely |
