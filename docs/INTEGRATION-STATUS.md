# Integration status: what's wired, what isn't

The three parts of this project each used to believe they owned game state. This document
records what is now connected, what is deliberately left inert, and what is still missing.

Last updated for branch `frontend-backend-fusion`.

## The three processes

| Process | Port | Started by | Required? |
|---|---|---|---|
| Python game server (FastAPI) | 8000 | `make backend` | Yes. Holds all authoritative state. |
| Vite dev server (React) | 5173 | `make frontend` | Yes. Proxies `/api` and `/ws` to :8000. |
| SmartSpectra sidecar (Node) | 3001 | `make spectra` | No. Without it you lose vitals only. |

`make dev` runs the first two. `make dev-all` runs all three.

---

## Done

### The frontend is driven by the server

The React app used to render from `src/mock/data.ts` and keep round progress in the query
string, so two players on the same code played two unrelated games. Now:

- `src/session.ts` persists the `PlayerSession` the backend mints on create/join. The
  `player_id` it holds is required by the websocket (which closes `4403` without it),
  frame upload, start, restart and leave — so this had to exist before anything else.
- `src/game.ts` (`useGame`, `useFollowServerPhase`) makes `state.phase` the only
  navigation authority. The host pressing start moves everyone; a reload lands you back
  where the game actually is.
- `useServerCountdown` anchors to `round.ends_at` corrected by `clockOffsetMs`.
- `types.ts` mirrors `models.py` field-for-field. **Keep it that way** — it is hand-written
  on purpose so drift shows up as a type error. The backend serves OpenAPI at
  `http://localhost:8000/openapi.json` if you would rather generate it.

### One camera

`useCamera` was deleted. It called `getUserMedia` independently of `useSmartSpectra`,
which meant two `MediaStream`s off one device. `useSmartSpectra` now owns the camera and
feeds both consumers from one stream:

- raw RGBA at camera rate → the sidecar (vitals)
- JPEG stills via `captureFrame()` → the game server (scoring)

### Real frame processing (`PROCESSOR=gemini`)

`app/processing/gemini.py` classifies the actual image. `dummy` derives a label from the
frame's SHA-256, so identical bytes always produce the same "emotion" and the player's face
is irrelevant — fine for tests, useless as a game.

The model is constrained by a response schema to `prompts.TARGET_LABELS` plus `"none"`.
Scoring is `label == round.target`, so an off-vocabulary label could never win a point.

| `PROCESSOR` | Needs | Behaviour |
|---|---|---|
| `dummy` (default) | nothing | Label from frame hash. Deterministic, ignores the face. |
| `gemini` | `GEMINI_API_KEY` | Real vision classification. Fails at **startup** if the key is missing. |
| `custom` | your code | Still a stub: every frame fails with `processing_failed`. |

### Round narration (gap 7)

`geminiprompts.py` and `voicegen.py` were standalone scripts that nothing imported — and
`voicegen.generate_for_prompt` picked *its own* prompt, so even if called it would have
narrated a different prompt than the round in play. `app/game/voice.py` wraps them for the
engine: it narrates the prompt the round actually chose, runs off the round's critical
path, and degrades in two independent steps.

| Keys present | Result |
|---|---|
| Both | Gemini writes a tagged line, ElevenLabs speaks it. `voice_line` + `audio_id`. |
| Gemini only | Gemini line, no audio. `audio_id` is `null`. |
| ElevenLabs only | `prompts.py` text spoken as written. |
| Neither | No narration. `/api/health` reports `voice.enabled: false`. |

Generation takes seconds, so the engine starts it as a background task and patches the
round via a `voice_ready` event. A round is **never** delayed waiting for audio, and a line
that resolves after its round has moved on is discarded rather than shown on the next one.
Verified live: with deliberately invalid keys both vendors were rejected, two warnings were
logged, `voice_line` fell back to the prompt text, and the round ran untouched.

### Vitals endpoint — intentionally inert (gap 4)

`POST /api/rooms/{room_id}/vitals` exists so the SmartSpectra readings stop being invisible
to the server. They are stored on the player, broadcast in every snapshot, and **never an
input to scoring**.

This is a decision, not an unfinished edge. The numbers are computed in the player's own
browser from their own camera, so the server cannot verify them; paying points for
self-reported physiology would make the leaderboard forgeable by anyone willing to edit a
websocket frame. Points come only from `processor.label == round.target`, judged on a frame
the server itself received.

`tests/test_vitals.py::test_vitals_never_affect_scoring` is what stops this becoming
untrue by accident: a player with a 180 bpm pulse and a wrong face scores zero.

**If you ever want vitals to matter**, the honest route is to make the server the one that
holds the SmartSpectra session (sidecar → Python, not sidecar → browser → Python), so the
reading is not round-tripped through the thing being measured.

---

## Still missing

### 1. The in-browser flow has never been run

The whole fused client is verified by type-checking, lint, 20 logic unit tests, and every
client URL shape exercised against a live backend. **Nobody has clicked through
create → lobby → round → results in a real browser**, because no browser with a camera was
available in the environment this was built in.

Most likely to bite: the phase-redirect loop in `useFollowServerPhase`. Needs one run on a
machine with a webcam.

### 2. The SmartSpectra metric names are unknown

`useSmartSpectra` types measurements as `Record<string, any>` and `Round.tsx` reads
`m?.pulse` / `m?.breathing` on a guess. The real shape comes from `decodeMetrics()` in the
node SDK and has never been logged. Until someone runs the sidecar and prints one payload:

- the two vitals tiles may read `--` forever even when the sidecar is healthy;
- `useVitalsReporter` forwards only top-level finite numbers, so nested or array-shaped
  metrics are silently dropped (the endpoint rejects non-numbers with 422 by design).

This is the single cheapest unknown to close: run `make spectra`, read one `metrics`
message, and tighten the type.

### 3. No intermission deadline

The backend exposes `round.ends_at` but nothing for the gap between rounds. During
`scoring`, `round.ends_at` is already in the past, so the Leaderboard says "next round
incoming…" with no countdown rather than guessing.

Fix: add `scoring_ends_at` (or a generic `phase_ends_at`) to `GameState`, set it in
`_end_round` from `intermission_seconds`, and point `useServerCountdown` at it.

### 4. House rules are read-only

The Lobby shows `config.rounds_per_game`, `round_seconds` and `points_per_correct` from the
server. The original design had segmented pickers for rounds and countdown; they were
removed because **no endpoint changes them** — they are process-level env config.

Fix: per-room overrides on `GameState.config`, plus `PATCH /api/rooms/{id}/config` (host
only, lobby phase only).

### 5. The deep-scan modal is still mocked

`components/DeepScanSummary.tsx` is the only remaining consumer of `src/mock/data.ts`. It
shows `peakPulse`, `hrv`, `topExpression`, `signalConfidence` and `pulseWave` — none of
which exist anywhere in the backend. Fabricating them from nothing seemed worse than
leaving the modal honestly mocked.

Fix needs a decision first: per-round vitals history would have to be stored (today only
the *latest* sample is kept per player), and HRV/blink/speech detection does not exist in
either the processor or the sidecar.

### 6. Metrics with no source anywhere

The design's vocabulary and the backend's do not fully overlap. Mapped so far:

| Design | Source now |
|---|---|
| total aura | `player.points` |
| this round | `round.points_awarded[player_id]` |
| damage match % | `result.confidence * 100` |
| server read / matched | `result.label` vs `round.target` |
| pulse, breathing | SmartSpectra sidecar (display only) |
| **blinks** | **nothing** — tile removed |
| **talking** | **nothing** — tile removed |

Blink and speech detection exist in neither the processor nor the sidecar. The tiles were
replaced with the server's real verdict rather than left showing invented numbers.

### 7. Lobby "rage quit" does not free the seat

`LeaveGame` (used on the Round and Leaderboard screens) calls `POST /leave` properly. The
Lobby's header uses the shared `Header` component, whose back link is a plain `<Link>` to
`/` — so leaving from the lobby relies on the websocket dropping plus the 60s
`empty_room_grace_seconds` reaper.

### 8. Autoplay may block the narration

`useNarration` calls `audio.play()` when `audio_id` arrives. Browsers require a prior user
gesture for audio; creating or joining a lobby is a click, which normally satisfies it, but
a blocked play is reported as `blocked: true` and the round screen falls back to showing
the line as text. Untested in a real browser (see #1).

### 9. Operational gaps

- **Single process only.** `InMemoryRoomStore` and `ConnectionManager` are in-process, so
  two backend replicas would not see each other's rooms or broadcasts. `store.py` documents
  the Redis swap.
- **No auth.** Anyone with a `room_id` and a `player_id` can act as that player. `player_id`
  is an unguessable token, which is the only thing protecting a seat.
- **Media and audio on local disk.** `MediaStore` and `VoiceStore` write to `MEDIA_DIR`;
  both need object storage for more than one host.
- **Sidecar is single-tenant-ish.** `server.js` opens one SDK session per browser
  connection and its own comment flags that concurrent-session licensing needs confirming
  with Presage.
- **Sidecar bandwidth.** 640×480×4 bytes = 1.17 MiB per frame; at ~30 fps that is roughly
  35 MiB/s (~280 Mbps) per player over the websocket. The `bufferedAmount < 8 MB` guard
  means frames are dropped silently on any real network. Sending JPEG or a smaller
  resolution to the sidecar would cut this by orders of magnitude.

---

## Configuration that is easy to get wrong

Every value is documented in `backend/.env.example`, `frontend/.env.example` and
`frontend/src/smart-spectra/.env.example`. The three that fail confusingly:

1. **`WEB_ORIGIN` (sidecar)** — `server.js` does an exact string match on the browser's
   `Origin` header. While it is unset, *every* connection is rejected with 403, including
   from localhost. Must include scheme and port, no trailing slash.
2. **`SMARTSPECTRA_API_KEY` (sidecar)** — the process throws on boot without it.
3. **`VITE_SPECTRA_WS_URL` (frontend)** — must match the sidecar's `PORT`. Defaults to
   `ws://localhost:3001`.

`GET /api/health` reports which optional features are actually live — the fastest way to
answer "why is there no audio" or "why is every face scored by a hash":

```json
{
  "processor": "dummy",
  "voice": { "enabled": false, "writes_lines": false, "speaks": false },
  "vitals_enabled": true
}
```

## A stale environment looks like a code bug

Both lockfiles are correct, but a checkout from before these changes will be missing
dependencies and fail in ways that look unrelated:

- missing `google-genai` → the backend imports fine (the AI SDKs are imported lazily on
  purpose) but `PROCESSOR=gemini` and Gemini voice lines fail;
- missing `react-router-dom` / `ws` / `dotenv` → `npm run build` fails with ten
  `Cannot find module` errors.

`make install` fixes both.
