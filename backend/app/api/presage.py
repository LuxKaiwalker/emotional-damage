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

from app.api.deps import EngineDep, MediaDep, SettingsDep
from app.capture.media import MediaStore
from app.game.engine import AlreadyPassed, GameEngine, GameError
from app.models import ExpressionReport, Phase
from app.processing.presage import PRESAGE_EXPRESSIONS, READINGS, judge, result_for

router = APIRouter(prefix="/internal/presage", tags=["presage"])


@router.post("/expressions", status_code=202)
async def report_expression(
    body: ExpressionReport,
    engine: EngineDep,
    media: MediaDep,
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
        scored = await _score_if_hit(
            engine, media, room, body.room_id, body.player_id, settings.presage_max_age_ms / 1000
        )
    return {"status": "recorded", "scored": scored}


async def _score_if_hit(
    engine: GameEngine,
    media: MediaStore,
    room,
    room_id: str,
    player_id: str,
    max_frame_age_s: float,
) -> bool:
    """Pass the player the moment Presage sees the asked-for face.

    Frame uploads arrive every CAPTURE_INTERVAL_MS, so judging only on them made a
    correct face wait up to that long, plus the upload, before it counted. A hit is
    scored here instead, through the same submission path an upload takes, so the rate
    limit, the already-passed check and speed points (from `received_at`, now) all hold.
    Misses are left to the uploads: a submission per reading would mean a room-wide state
    broadcast several times a second per player, on a single core.

    `accepted.target` is the player's *own* target, so the result is judged against the
    right face even if they advanced between the two awaits -- `apply_result` drops it in
    that case rather than paying for a face they have left.

    The submission has no frame of its own, so it borrows the player's newest upload --
    at most one capture tick old -- for the hall of faces to show. Only one as young as
    a reading has to be to score, so the picture is of the face that was scored.
    """
    # Whichever face this player is on -- the shared round in classic, their own cursor in
    # blitz. Asking the engine keeps this path from having to know which mode it is in.
    face = engine.current_face(room, player_id)
    if face is None:
        return False
    _, target = face
    reading = READINGS.latest(room_id, player_id)
    if reading is None:
        return False
    label, confidence = judge(reading, target)
    # The threshold is checked *before* submitting, not just by `apply_result`. A reading
    # that cannot pass would otherwise spend the player's min_frame_interval_ms slot on a
    # submission with no upside -- which in blitz costs them faces.
    if label != target or confidence < engine.pass_threshold(room):
        return False

    try:
        accepted = await engine.submit_frame(room_id, player_id, size=0)
    except (AlreadyPassed, GameError):
        # Passed meanwhile, rate-limited by an upload a moment ago, or the round ended.
        return False
    await media.borrow_latest(room_id, player_id, accepted.submission.id, max_frame_age_s)
    result = result_for(
        reading,
        accepted.target,
        {"processor": "presage", "source": "reading", "prompt": accepted.prompt, "target": accepted.target},
    )
    await engine.apply_result(room_id, accepted.submission.id, result)
    return True
