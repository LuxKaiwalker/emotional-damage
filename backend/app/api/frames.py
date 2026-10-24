from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.api.deps import EngineDep, FrameQueueDep, MediaDep, SettingsDep
from app.capture.queue import FrameJob
from app.game.engine import GameError

router = APIRouter(prefix="/api", tags=["capture"])

ALLOWED_TYPES = {"image/jpeg", "image/jpg"}


@router.post("/rooms/{room_id}/frames", status_code=202)
async def upload_frame(
    room_id: str,
    response: Response,
    engine: EngineDep,
    frames: FrameQueueDep,
    media: MediaDep,
    settings: SettingsDep,
    player_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Ingest one camera still.

    Returns 202 + submission_id; the score arrives later over the room's websocket.
    A refused frame is normal operation for a live camera, not a client bug -- the
    rate-limited and overloaded cases answer 200 with `skipped` so the client can
    simply carry on to its next tick.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"expected JPEG, got {file.content_type!r}")

    data = await file.read()
    if not data:
        raise HTTPException(400, "empty frame")
    if len(data) > settings.max_frame_bytes:
        raise HTTPException(413, f"frame exceeds {settings.max_frame_bytes} bytes")

    try:
        submission = await engine.submit_frame(room_id, player_id, size=len(data))
    except GameError as exc:
        if exc.status_code == 429:
            response.status_code = status.HTTP_200_OK
            return {"skipped": True, "reason": "rate_limited"}
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    room = engine.require_room(room_id)
    assert room.state.round is not None  # submit_frame enforces phase == ROUND
    path = await media.write(room_id, submission.id, data)

    accepted = frames.submit(
        FrameJob(
            room_id=room_id,
            player_id=player_id,
            submission_id=submission.id,
            round_no=submission.round_no,
            prompt=room.state.round.prompt,
            path=path,
        )
    )
    if not accepted:
        response.status_code = status.HTTP_200_OK
        return {"skipped": True, "reason": "overloaded"}

    return {"submission_id": submission.id, "skipped": False}


@router.get("/media/{submission_id}")
async def get_frame(submission_id: str, media: MediaDep) -> Response:
    """Serve a stored frame. Debugging and round replay; not part of the game loop."""
    path = media.find(submission_id)
    if path is None:
        raise HTTPException(404, "frame not found or expired")
    return Response(content=await media.read(path), media_type="image/jpeg")
