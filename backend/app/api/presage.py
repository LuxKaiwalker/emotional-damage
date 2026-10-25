"""Where the SmartSpectra sidecar delivers Presage expression readings.

Outside /api on purpose: nginx only proxies /api and /ws, so this is reachable from the box
itself and nothing else. The shared token is the second lock, for any deployment that
proxies more than that.

Unlike POST /api/rooms/{id}/vitals, these readings *are* scoring input under
PROCESSOR=presage. They come from the sidecar, not the browser, computed from the same
camera feed a Gemini judge would see as a JPEG -- so they are exactly as trustworthy as the
frames themselves.
"""

import secrets

from fastapi import APIRouter, Header, HTTPException

from app.api.deps import EngineDep, SettingsDep
from app.game.engine import AlreadyPassed, GameEngine, GameError
from app.models import ExpressionReport, Phase
from app.processing.presage import PRESAGE_EXPRESSIONS, READINGS, judge, result_for

router = APIRouter(prefix="/internal/presage", tags=["presage"])


@router.post("/expressions", status_code=202)
async def report_expression(
    body: ExpressionReport,
    engine: EngineDep,
    settings: SettingsDep,
    x_presage_token: str | None = Header(default=None),
) -> dict:
    token = settings.presage_ingest_token
    if not token:
        raise HTTPException(503, "presage ingest is disabled: PRESAGE_INGEST_TOKEN is unset")
    if not secrets.compare_digest(x_presage_token or "", token):
        raise HTTPException(401, "bad presage token")

    unknown = set(body.scores) - set(PRESAGE_EXPRESSIONS)
    if unknown or not body.scores:
        raise HTTPException(422, f"unknown expressions: {sorted(unknown)}")
    if any(not 0 <= v <= 100 for v in body.scores.values()):
        raise HTTPException(422, "expression scores are percentages, 0 to 100")

    try:
        room = engine.require_room(body.room_id)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if body.player_id not in room.state.players:
        raise HTTPException(404, "unknown player for this room")

    READINGS.put(
        body.room_id,
        body.player_id,
        {name: v / 100 for name, v in body.scores.items()},
        body.stable,
    )
    scored = False
    if settings.processor == "presage":
        scored = await _score_if_hit(engine, room, body.room_id, body.player_id)
    return {"status": "recorded", "scored": scored}


async def _score_if_hit(engine: GameEngine, room, room_id: str, player_id: str) -> bool:
    """Pass the player the moment Presage sees the asked-for face.

    Frame uploads arrive every CAPTURE_INTERVAL_MS, so judging only on them made a
    correct face wait up to that long, plus the upload, before it counted. A hit is
    scored here instead, through the same submission path an upload takes, so the rate
    limit, the already-passed check and speed points (from `received_at`, now) all hold.
    Misses are left to the uploads: a submission per reading would mean a room-wide state
    broadcast several times a second per player, on a single core.
    """
    state = room.state
    if state.phase is not Phase.ROUND or state.round is None or player_id in state.round.passed:
        return False
    reading = READINGS.latest(room_id, player_id)
    target = state.round.target
    if reading is None or judge(reading, target)[0] != target:
        return False

    try:
        accepted = await engine.submit_frame(room_id, player_id, size=0)
    except (AlreadyPassed, GameError):
        # Passed meanwhile, rate-limited by an upload a moment ago, or the round ended.
        return False
    result = result_for(
        reading,
        accepted.target,
        {"processor": "presage", "source": "reading", "prompt": accepted.prompt, "target": accepted.target},
    )
    await engine.apply_result(room_id, accepted.submission.id, result)
    return True
