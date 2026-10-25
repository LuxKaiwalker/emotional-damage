import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import frames, highscores as highscores_api, rooms, vitals, voice, ws
from app.api.deps import FrameQueueDep, RoomStoreDep, SettingsDep
from app.capture.media import MediaStore
from app.capture.queue import FrameQueue
from app.config import Settings, get_settings
from app.game.engine import GameEngine
from app.game.highscores import HighScoreStore
from app.game.hub import ConnectionManager
from app.game.store import InMemoryRoomStore
from app.game.voice import VoiceStore, VoiceStudio
from app.processing.registry import get_processor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    media = MediaStore(settings.media_dir, settings.media_ttl_seconds)
    store = InMemoryRoomStore()
    hub = ConnectionManager()
    # Audio lives beside the frames so one MEDIA_DIR is all a deployment has to mount.
    voice_store = VoiceStore(settings.media_dir / "voice", settings.voice_ttl_seconds)
    studio = VoiceStudio(voice_store, settings)
    highscores = HighScoreStore(settings.highscores_path or settings.media_dir / "highscores.json")
    engine = GameEngine(store, hub, settings, voice=studio, highscores=highscores)
    queue = FrameQueue(
        engine=engine,
        media=media,
        processor=get_processor(settings.processor),
        maxsize=settings.queue_maxsize,
        worker_count=settings.worker_count,
    )

    app.state.media = media
    app.state.store = store
    app.state.hub = hub
    app.state.engine = engine
    app.state.highscores = highscores
    app.state.frames = queue
    app.state.voice_store = voice_store
    app.state.voice = studio

    queue.start()
    reapers = [
        asyncio.create_task(media.reap_forever(), name="media-reaper"),
        asyncio.create_task(engine.reap_empty_rooms_forever(), name="room-reaper"),
        asyncio.create_task(voice_store.reap_forever(), name="voice-reaper"),
    ]
    try:
        yield
    finally:
        for reaper in reapers:
            reaper.cancel()
        await asyncio.gather(*reapers, return_exceptions=True)
        await queue.stop()
        await engine.shutdown()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="emotional-damage",
        summary="Camera-driven multiplayer game server. Holds the authoritative state.",
        lifespan=lifespan,
    )
    app.state.settings = settings or get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app.state.settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(rooms.router)
    app.include_router(frames.router)
    app.include_router(vitals.router)
    app.include_router(voice.router)
    app.include_router(ws.router)
    app.include_router(highscores_api.router)

    @app.get("/api/health", tags=["ops"])
    async def health(queue: FrameQueueDep, settings: SettingsDep, store: RoomStoreDep) -> dict:
        studio: VoiceStudio = app.state.voice
        return {
            "status": "ok",
            "processor": settings.processor,
            "queue_depth": queue.depth,
            "frames_dropped": queue.dropped,
            "rooms": store.count(),
            # Which optional features are actually live. Checking this is the fastest way
            # to answer "why is there no audio" or "why is every face scored by a hash".
            "voice": {
                "enabled": studio.enabled,
                "writes_lines": studio.writes_lines,
                "speaks": studio.speaks,
            },
            "vitals_enabled": settings.vitals_enabled,
        }

    return app


app = create_app()
