"""Serving Uncle Damage's generated audio.

The round carries `voice_line` (text) and `audio_id`; the client fetches the mp3 from
here. Audio is generated per round and reaped on a TTL, so a 404 here is ordinary -- an
old round, or a round whose narration failed or was never configured. Clients should treat
`voice_line` as the thing that is always there and the audio as a bonus.
"""

from fastapi import APIRouter, HTTPException, Response

from app.api.deps import VoiceStoreDep

router = APIRouter(prefix="/api", tags=["voice"])


@router.get("/voice/{audio_id}")
async def get_voice(audio_id: str, store: VoiceStoreDep) -> Response:
    path = store.find(audio_id)
    if path is None:
        raise HTTPException(404, "audio not found or expired")
    return Response(content=await store.read(path), media_type="audio/mpeg")
