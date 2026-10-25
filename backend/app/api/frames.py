from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.api.deps import EngineDep, FrameQueueDep, MediaDep, SettingsDep
from app.capture.queue import FrameJob
from app.game.engine import AlreadyPassed, GameError

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
        raise HTTPException(415, "Camera frames have to be JPEG images.")

    data = await file.read()
    if not data:
        raise HTTPException(400, "That camera frame came through empty.")
    if len(data) > settings.max_frame_bytes:
        raise HTTPException(
            413, f"That camera frame is too big (the limit is {settings.max_frame_bytes // 1024} KB)."
        )

    try:
        accepted = await engine.submit_frame(room_id, player_id, size=len(data))
    except AlreadyPassed:
        # The client stops capturing once the snapshot says it passed; this covers the
        # frames already on their way when that snapshot landed.
        response.status_code = status.HTTP_200_OK
        return {"skipped": True, "reason": "passed"}
    except GameError as exc:
        if exc.status_code == 429:
            response.status_code = status.HTTP_200_OK
            return {"skipped": True, "reason": "rate_limited"}
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    submission = accepted.submission
    path = await media.write(room_id, submission.id, data)

    queued = await frames.submit(
        FrameJob(
            room_id=room_id,
            player_id=player_id,
            submission_id=submission.id,
            round_no=submission.round_no,
            prompt=accepted.prompt,
            target=accepted.target,
            path=path,
        )
    )
    if not queued:
        # The queue has already settled the submission; nothing is left pending.
        response.status_code = status.HTTP_200_OK
        return {"skipped": True, "reason": "overloaded"}

    return {"submission_id": submission.id, "skipped": False}


@router.get("/media/{submission_id}")
async def get_frame(submission_id: str, media: MediaDep) -> Response:
    """Serve a stored frame. Debugging and round replay; not part of the game loop."""
    path = media.find(submission_id)
    if path is None:
        raise HTTPException(404, "That frame has expired.")
    return Response(content=await media.read(path), media_type="image/jpeg")
