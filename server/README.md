# CSSocialGame Server

Go backend for the CSSocialGame Godot client. Single binary serving auth, room registry, gameplay sync, and LiveKit token minting.

> Full plan lives in `../docs/obsidian` — start with `Architecture.md` and `Networking - Overview.md`.

## Phase 1 status

| Sub-phase | What | Status |
| --- | --- | --- |
| 1.1 — Bootstrap | Go module, `/health`, Postgres via docker-compose, schema, middleware | ✅ |
| 1.2 — Auth | `POST /auth/register|verify|login|refresh|logout`, `GET /me`, JWT, bcrypt, refresh-token rotation, per-IP rate limit | ✅ |
| 1.3 — WebSocket + Godot integration | `GET /ws?token=<jwt>`, `hello` round-trip, Godot login scene, `NetworkBackend` real impl, duplicate active account sessions rejected | ✅ |

## Prerequisites

- **Go 1.23+** — download from <https://go.dev/dl/> and install
- **Docker Desktop** — running (the Postgres container needs the daemon)
- Optional: **psql** client for manual DB poking

Verify after installing:

```powershell
go version          # should print: go version go1.23.x ...
docker version      # should print Server: section without errors
```

## Setup

From the `server/` folder:

```powershell
# One-time
copy .env.example .env
go mod tidy                  # pulls dependencies, writes go.sum

# Every time
docker-compose up -d         # start Postgres in the background
go run ./cmd/server          # start the API on :8080
```

The server auto-loads `.env` from its working directory at startup. Missing `.env` is fine — real OS env vars always win. So `docker-compose` for prod sets env directly on the service, no `.env` file needed there.

Verify the server is up:

```powershell
curl http://localhost:8080/health
# → ok
```

If the DB isn't reachable you'll see `db unreachable` and a 503 — check `docker-compose ps` and `docker-compose logs postgres`.

## Layout

```
server/
├── cmd/server/main.go              # entrypoint
├── internal/
│   ├── auth/                       # auth service, handlers, JWT, refresh tokens
│   ├── config/config.go            # env-driven config
│   ├── db/
│   │   ├── db.go                   # pgx pool
│   │   └── migrations/
│   │       └── 001_init.sql        # users + refresh_tokens
│   ├── httpx/middleware.go         # request id, access log, panic recover
│   └── ws/                         # control WebSocket + active-session registry
├── docker-compose.yml              # Postgres only; server runs on host for fast iteration
├── go.mod
├── .env.example
└── README.md
```

## Stack (decided in vault)

| Concern | Choice |
| --- | --- |
| HTTP routing | stdlib `net/http` (Go 1.22+ `ServeMux` patterns: `mux.HandleFunc("GET /foo", ...)`) |
| Database | `jackc/pgx/v5/pgxpool`, hand-written SQL (sqlc later if query count balloons) |
| Migrations | Plain `.sql` files in `internal/db/migrations`, auto-loaded by Postgres on first init. Adopt `golang-migrate` when we need iterative migrations. |
| Auth | `golang.org/x/crypto/bcrypt` + `golang-jwt/jwt/v5` (1.2) |
| WebSocket | `coder/websocket` (1.3) |
| Logging | stdlib `log/slog`, text handler, level from `LOG_LEVEL` env |
| Config | env vars only (12-factor); `.env` for local dev |
| IDs | ULID (`oklog/ulid/v2`) for users and refresh_tokens |

## Database

### Connecting manually

```powershell
docker-compose exec postgres psql -U cssocial -d cssocial
```

Or from the host with a Postgres client (uses port 5433 to avoid colliding with native installs):

```powershell
psql -h localhost -p 5433 -U cssocial -d cssocial
```

### Port note

Docker's Postgres is mapped to host port **5433** (not the default 5432). This is intentional — a lot of dev machines already have a native Postgres service on 5432 (Windows installer, Supabase CLI, pgAdmin's bundled server, etc.), and the native install wins the race. We sidestep the conflict by using 5433 on the host. Container-internal port is still 5432.

## Testing the auth endpoints

After `go run ./cmd/server` is up. **Pick one of two approaches** — `Invoke-RestMethod` is more PowerShell-native and dodges the quoting pitfalls; `curl.exe` works too if you keep JSON in single quotes.

### Option A — `Invoke-RestMethod` (recommended on Windows)

```powershell
$base = "http://localhost:8080"

# 1. Register — note the server log for the verification token
$reg = Invoke-RestMethod -Method POST -Uri "$base/auth/register" `
    -ContentType "application/json" `
    -Body (@{ email = "kurt@example.com"; password = "supersecret"; display_name = "kurt" } | ConvertTo-Json)
$reg
# → user_id : 01HXYZ...

# 2. Verify (optional — login works without verification for now).
#    Grab the actual token from the server's stdout log line:
#    "verification token issued ... verify_token=<COPY THIS>"
$verifyToken = "<paste from server log>"
Invoke-RestMethod -Method POST -Uri "$base/auth/verify" `
    -ContentType "application/json" `
    -Body (@{ token = $verifyToken } | ConvertTo-Json)

# 3. Login → access_token + refresh_token
$login = Invoke-RestMethod -Method POST -Uri "$base/auth/login" `
    -ContentType "application/json" `
    -Body (@{ email = "kurt@example.com"; password = "supersecret" } | ConvertTo-Json)
$login

# 4. Hit a protected endpoint
Invoke-RestMethod -Uri "$base/me" -Headers @{ Authorization = "Bearer $($login.access_token)" }

# 5. Refresh (rotates — old refresh becomes invalid)
$refreshed = Invoke-RestMethod -Method POST -Uri "$base/auth/refresh" `
    -ContentType "application/json" `
    -Body (@{ refresh_token = $login.refresh_token } | ConvertTo-Json)
$refreshed

# 6. Logout (revokes the *current* refresh token — use the rotated one)
Invoke-RestMethod -Method POST -Uri "$base/auth/logout" `
    -ContentType "application/json" `
    -Body (@{ refresh_token = $refreshed.refresh_token } | ConvertTo-Json)
```

### Option B — `curl.exe` (always single-quote the body)

PowerShell-safe rule: JSON body **always in single quotes** so PowerShell doesn't try to interpret `\"`. The body is passed verbatim to `curl.exe`.

```powershell
# 1. Register
curl.exe -X POST http://localhost:8080/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email":"kurt@example.com","password":"supersecret","display_name":"kurt"}'

# 2. Verify — paste the actual token from the server stdout log
curl.exe -X POST http://localhost:8080/auth/verify `
  -H "Content-Type: application/json" `
  -d '{"token":"PASTE-REAL-TOKEN-HERE"}'

# 3. Login
curl.exe -X POST http://localhost:8080/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email":"kurt@example.com","password":"supersecret"}'

# 4. /me — paste the actual access_token from step 3
curl.exe http://localhost:8080/me -H "Authorization: Bearer PASTE-ACCESS-TOKEN"

# 5. Refresh — paste the actual refresh_token from step 3
curl.exe -X POST http://localhost:8080/auth/refresh `
  -H "Content-Type: application/json" `
  -d '{"refresh_token":"PASTE-REFRESH-TOKEN"}'

# 6. Logout — paste the ROTATED refresh_token from step 5
curl.exe -X POST http://localhost:8080/auth/logout `
  -H "Content-Type: application/json" `
  -d '{"refresh_token":"PASTE-ROTATED-REFRESH-TOKEN"}'
```

> [!warning] Don't mix the two
> Don't use `"{\"key\":\"val\"}"` (bash-style escaped JSON) in PowerShell. PowerShell's double-quote escaping rules differ from bash's, and `\"` ends up reaching `curl.exe` as a literal `\"`, which the JSON decoder rejects with `invalid character '\\'`. Use single quotes (Option B) or skip curl entirely (Option A).

### Error responses

All errors come back as JSON in a standard envelope:

```json
{ "error": { "code": "invalid_credentials", "message": "invalid email or password" } }
```

Codes returned by /auth/*: `bad_request`, `validation_failed` (with `details` array), `email_taken`, `display_name_taken`, `invalid_credentials`, `token_expired`, `not_authenticated`, `refresh_invalid`, `verification_invalid`, `rate_limited`, `internal`.

### Rate limit

5 requests instantly, then ~5/minute sustained per source IP, across all `/auth/*` endpoints combined. Returns 429 with `rate_limited` when exceeded. Bucket lives in process memory — restarts reset the counts (fine at our scale).

## Database

### Connecting manually

The schema lives in `internal/db/migrations/*.sql` and is loaded by Postgres only on FIRST volume initialization. To re-apply (DROPS ALL DATA):

```powershell
docker-compose down -v
docker-compose up -d
```

### Inspecting

```sql
\dt                              -- list tables
\d users                         -- describe users table
SELECT id, email, display_name, verified, created_at FROM users LIMIT 10;
```

## Repo decision

The server lives in `/server` (this folder) inside `pdc_final_project` on the `port/godot` branch — same repo as the Godot client. Reasons:

- Keeps the Phase 1–10 scope reviewable as one PR series
- One `git clone` for any contributor to get both sides
- Server can be split out into its own repo after the coursework grade lands (Open Questions in vault)

The module path `github.com/CS-StudentGroup/pdc_final_project/server` reflects this. If/when the server moves out, the path becomes `github.com/<org>/cssocialgame-server` and we update one line in `go.mod` + imports.

## Stopping

```powershell
# Stop the Go server: Ctrl+C
docker-compose down                 # stop Postgres, keep data
docker-compose down -v              # also wipe pgdata volume (destroys all users/rooms/etc.)
```
