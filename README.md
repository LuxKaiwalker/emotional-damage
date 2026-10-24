# emotional damage

Boilerplate for a camera-driven multiplayer game. Every player's browser captures camera
stills and POSTs them to a Python backend; the backend processes them, holds the
**authoritative game state**, and pushes that state to all players over WebSocket.

The game rules and the frame processing are deliberately stubs. The plumbing is real.

## Run it

```bash
make install     # backend venv + npm install
make dev         # API on :8000, UI on :5173
make test        # backend test suite
```

Then open <http://localhost:5173> in **two or three tabs**: tab 1 creates a room, the others
join with the 4-character code. Session state lives in `sessionStorage`, so each tab is a
separate player.

API docs: <http://localhost:8000/docs>

## How it fits together

```
 Player tab A ─┐   POST /api/rooms/{id}/frames (multipart jpeg)  ──> ┌──────────────┐
 Player tab B ─┼──────────────────────────────────────────────────>  │   FastAPI    │
 Player tab C ─┘                                                     │  MediaStore  │
       ▲          WS /ws/rooms/{id}  (authoritative state)           │  FrameQueue  │
       └─────────────────────────────────────────────────────────────│  N workers   │
                                                                     │  Processor   │
                                                                     │  GameEngine  │
                                                                     └──────────────┘
```

Two channels on purpose:

- **Frames go over HTTP POST.** Inspectable in devtools, rate-limitable, replayable from
  disk — and a slow upload can never stall the state channel.
- **State comes back over WebSocket.** The client renders what the server sent and computes
  no game state of its own. An upload response carries only `202 {submission_id}`; the score
  arrives later as a snapshot.

The authoritative-state rule, in one line: every mutation goes through a `GameEngine` method
that holds that room's `asyncio.Lock`, bumps `seq`, and ends in a broadcast. Clients drop any
snapshot whose `seq` isn't strictly newer, so a reconnect resyncs instead of drifting.

Frame processing is async by design: upload → bounded queue → worker pool → `Processor` →
`engine.apply_result()` → broadcast. The queue is bounded because when players out-produce
the processor, the right move for live camera input is to drop *stale* frames, not to grow a
backlog. Each round keeps one submission slot per player — newest frame wins — and points are
committed to totals when the **server** ends the round.

## Game loop

`LOBBY → ROUND(prompt, deadline) → SCORING → … → GAME_OVER`, driven by one `asyncio.Task` per
room (`GameEngine._run_game`). The client's countdown is anchored to the server's `ends_at`
with a measured clock offset, so the UI timer can't disagree with the server that ends the round.

## Where to put your own code

| What | Where |
| --- | --- |
| Real frame processing | `backend/app/processing/custom.py`, then `PROCESSOR=custom` |
| Game rules, phases, scoring | `backend/app/game/engine.py` |
| Round prompts | `backend/app/game/prompts.py` |
| Multi-process state (Redis) | `backend/app/game/store.py` |
| Frames in object storage | `backend/app/capture/media.py` |
| Tunables (round length, limits) | `backend/app/config.py`, `backend/.env` |

A blocking model (OpenCV, torch, mediapipe) must not run directly in `process()` — hand it to
a thread with `loop.run_in_executor`. `custom.py` has the sketch.

## Gotchas worth knowing up front

**`getUserMedia` requires a secure context.** `http://localhost` qualifies, so local dev is
fine. Opening the UI from a phone or another machine over plain HTTP gives you *no camera*,
usually with no obvious error. Either serve over HTTPS (e.g. `mkcert` + `server.https` in
`vite.config.ts`), or launch Chrome with
`--unsafely-treat-insecure-origin-as-secure=http://192.168.x.x:5173 --user-data-dir=/tmp/chrome-dev`.

**`player_id` is not authentication.** It's an opaque id handed out at join and passed back as
a form field / query param. Fine for a prototype on your LAN; add real auth before anything else.

**State is in-process.** One backend process only — `--workers 2` would give you two
independent game worlds. See `store.py` for the Redis swap.

**Frames are written to `backend/.media/`** and reaped after `MEDIA_TTL_SECONDS` (15 min).
`GET /api/media/{submission_id}` serves one back; the debug panel uses it to show your last
uploaded frame.

## Endpoints

| Method | Path | |
| --- | --- | --- |
| `GET` | `/api/health` | status, processor, queue depth, frames dropped |
| `POST` | `/api/rooms` | create a room, returns host `player_id` + `join_code` |
| `POST` | `/api/rooms/{id}/join` | join by room id **or** join code |
| `GET` | `/api/rooms/{id}` | state snapshot (REST fallback for the WS) |
| `POST` | `/api/rooms/{id}/start` | host only, `?player_id=` |
| `POST` | `/api/rooms/{id}/frames` | multipart JPEG + `player_id` → `202 {submission_id}` |
| `GET` | `/api/media/{submission_id}` | the stored frame |
| `WS` | `/ws/rooms/{id}?player_id=` | state snapshots + events, server → client |

A refused frame is normal operation, not a client bug: rate-limited and overloaded cases
answer `200 {"skipped": true, "reason": ...}` so the client just carries on to its next tick.

## Tests

`backend/tests/` covers the full flow (create → join → start → upload → scored → `game_over`),
WS snapshot monotonicity, and the upload rejection matrix (wrong type, empty, oversized,
unknown player, wrong phase, rate-limited, newest-frame-wins). No frontend test runner —
add Vitest if you want one.
