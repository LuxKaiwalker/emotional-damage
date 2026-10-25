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
from app.game.engine import GameError
from app.models import ExpressionReport
from app.processing.presage import PRESAGE_EXPRESSIONS, READINGS

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
    return {"status": "recorded"}
