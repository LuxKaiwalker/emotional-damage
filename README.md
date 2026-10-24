# emotional damage

Boilerplate for a camera-driven multiplayer game. Every player's browser captures camera
stills and POSTs them to a Python backend; the backend processes them, holds the
**authoritative game state**, and pushes that state to all players over WebSocket.

The frame processing is deliberately a stub. The plumbing and the game rules are real.

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

### Scoring: one point per correct round

Every round names a `target` label alongside its prompt (`app/game/prompts.py`). A processor
hands back a `label` for each frame, and the rule is exactly one comparison:

```
submission.correct  ==  (result.label == round.target)
player.points       +=  1   # for each round whose last scored frame was correct
```

`points` is an integer and the only thing the scoreboard ranks on. `ProcessResult.score` and
`.confidence` survive as the raw read — shown in the UI, useful when debugging a model — but
they do not feed the total. A frame is judged the moment its result lands, so the UI can show
a hit immediately; the point itself is committed when the **server** ends the round, which is
also when a pending frame stops being worth anything.

Every `target` must be a label your processor can actually emit, or nothing will ever score.
`prompts.TARGET_LABELS` is that shared vocabulary, and the dummy processor draws its fake
answers from it for exactly this reason.

Two edges worth knowing, both of which bite harder the slower your processor is:

- A frame the server throws away under backpressure settles as `failed` with
  `error: "dropped_under_load"`. It never scores, but it never hangs on `pending` either —
  a silently abandoned submission would read as "still scoring" for the rest of the round.
- A result that arrives after its round was committed is recorded (the read is still worth
  showing) but deliberately left **unjudged**, `correct: null`. Showing a ✓ for a point the
  player can no longer be paid is worse than showing the raw read alone.

### Timers: the round deadline, and the game's

Two deadlines, and the game's always wins:

- **`round.ends_at`** — per round, `ROUND_SECONDS` long.
- **`game_ends_at`** — set when the host starts, `GAME_SECONDS` after that. A round that
  would overrun it is truncated to it, and once less than a second is left the game ends
  instead of starting another round. So `ROUNDS_PER_GAME` is a maximum, not a promise:
  `game_over` arrives with `reason` of `rounds_complete` or `time_up`.
- **Host-picked rounds** — in the lobby the host can pick 5 or 10 rounds
  (`POST /api/rooms/{id}/rounds`). That stretches the room's game timer to fit every
  round, so a picked count is always played in full and the deep scan lists all of them.

Both are absolute timestamps, anchored the same way client-side, so a long round and a long
game count down off the same measured clock offset.

### Rooms: codes, restarts, and destruction

A room is created with a 4-letter join code (`A-Z` only — digits invite `0`/`O` mix-ups when
a code gets read out loud) and is reachable by either its code or its room id. Codes are
unique across live rooms and recycled once a room is gone.

`POST /restart` is the host's way to play again: it clears every score, bumps `game_no`, and
returns the room to its **lobby** rather than straight into a game, which is what lets people
join between games. The host then starts it as usual. `game_over` is otherwise terminal —
`/start` from it is a 409.

A room dies with its players, two ways:

- **The last player calls `/leave`** → destroyed immediately, its running game cancelled and
  its sockets closed with code `4000`.
- **Everyone's socket drops** (closed tabs, dead wifi) → the room is marked empty and the
  reaper destroys it `EMPTY_ROOM_GRACE_SECONDS` later. The grace period is the point: a
  player who reloads the page gets their room back. A reconnect inside the window clears the
  mark. A room created by a client that never connects at all is on the same clock.

Leaving mid-game drops that player's submission slot too, and a departing host hands off to
the longest-tenured player still there, so the room never ends up with no one able to start.

## Where to put your own code

| What | Where |
| --- | --- |
| Real frame processing | `backend/app/processing/custom.py`, then `PROCESSOR=custom` |
| Game rules, phases, scoring | `backend/app/game/engine.py` |
| Round prompts and their target labels | `backend/app/game/prompts.py` |
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

**Rooms are destroyed when they empty out.** Both paths are deliberate, and both will
surprise you in dev if you forget them: `/leave` by the last player is immediate, and a room
with no live sockets is reaped after `EMPTY_ROOM_GRACE_SECONDS` (60). Short grace periods plus
a long debugger pause means your room disappears while you are reading the stack trace.

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
| `POST` | `/api/rooms/{id}/restart` | host only, after `game_over`: scores cleared, back to the lobby |
| `POST` | `/api/rooms/{id}/leave` | `?player_id=` → `{room_destroyed}`; the last one out closes the room |
| `POST` | `/api/rooms/{id}/frames` | multipart JPEG + `player_id` → `202 {submission_id}` |
| `GET` | `/api/media/{submission_id}` | the stored frame |
| `WS` | `/ws/rooms/{id}?player_id=` | state snapshots + events, server → client |

A refused frame is normal operation, not a client bug: rate-limited and overloaded cases
answer `200 {"skipped": true, "reason": ...}` so the client just carries on to its next tick.
A frame that is accepted and *then* dropped under load settles its submission as `failed`
rather than leaving it pending — see the scoring notes above.

## Tests

| File | What it pins down |
| --- | --- |
| `test_game_flow.py` | create → join → start → upload → scored → `game_over`, WS snapshot monotonicity |
| `test_capture.py` | the upload rejection matrix: wrong type, empty, oversized, unknown player, wrong phase, rate-limited, newest-frame-wins |
| `test_scoring.py` | one point per correct round, nothing for a wrong or missing answer, ranking order |
| `test_game_timer.py` | the game deadline truncating a round and ending the game early |
| `test_rooms.py` | join codes, capacity, host handoff, leaving, and both destruction paths |
| `test_backpressure.py` | every frame the server drops is settled, and a late result is not marked correct |
| `test_restart.py` | scores cleared, room identity kept, a second game played in the same room |

Scoring is asserted against `test-hit` / `test-miss` processors registered in `conftest.py`
via `processing.registry.register()` — the real rule is "label equals target" and the target
is picked at random, so a processor with a known verdict is the only way to assert on points.
Room lifecycle and the reaper are tested against a bare `GameEngine`, no HTTP in the way.

No frontend test runner — add Vitest if you want one.
