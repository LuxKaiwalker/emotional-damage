"""Where client-reported vitals land.

This endpoint exists so the SmartSpectra readings stop being invisible to the server: the
node sidecar used to hand pulse and breathing straight back to the browser that produced
them, and the authoritative game had no idea they existed.

It is deliberately a dead end for the rules. The samples are stored on the player and
broadcast in the snapshot so every client can show them, and nothing in the scoring path
reads them -- see `GameEngine.record_vitals`. That is not an oversight to be tidied up
later: the numbers are computed in the player's own browser from their own camera, so the
server cannot verify them, and paying points for self-reported physiology would make the
leaderboard forgeable by anyone willing to edit a websocket frame. Points come only from
`processor.label == round.target`, judged on a frame the server itself received.
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import EngineDep, SettingsDep
from app.game.engine import GameError
from app.models import VitalsReport

router = APIRouter(prefix="/api", tags=["vitals"])


@router.post("/rooms/{room_id}/vitals", status_code=202)
async def report_vitals(
    room_id: str,
    body: VitalsReport,
    engine: EngineDep,
    settings: SettingsDep,
) -> dict:
    """Record one vitals sample for a player. Accepted in any phase, scored in none."""
    if not settings.vitals_enabled:
        raise HTTPException(503, "Vitals are switched off on this server.")

    # Untrusted input that ends up in every snapshot, so it stays small and flat.
    if len(body.metrics) > settings.max_vitals_fields:
        raise HTTPException(
            413, f"Too many vitals in one report (the limit is {settings.max_vitals_fields})."
        )

    try:
        await engine.record_vitals(room_id, body.player_id, body.metrics)
    except GameError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return {"status": "recorded", "scored": False}
