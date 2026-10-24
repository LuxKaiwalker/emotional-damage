import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import frames, rooms, ws
from app.api.deps import FrameQueueDep, SettingsDep
from app.capture.media import MediaStore
from app.capture.queue import FrameQueue
from app.config import Settings, get_settings
from app.game.engine import GameEngine
from app.game.hub import ConnectionManager
from app.game.store import InMemoryRoomStore
from app.processing.registry import get_processor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    media = MediaStore(settings.media_dir, settings.media_ttl_seconds)
    store = InMemoryRoomStore()
    hub = ConnectionManager()
    engine = GameEngine(store, hub, settings)
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
    app.state.frames = queue

    queue.start()
    reaper = asyncio.create_task(media.reap_forever(), name="media-reaper")
    try:
        yield
    finally:
        reaper.cancel()
        await asyncio.gather(reaper, return_exceptions=True)
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
    app.include_router(ws.router)

    @app.get("/api/health", tags=["ops"])
    async def health(queue: FrameQueueDep, settings: SettingsDep) -> dict:
        return {
            "status": "ok",
            "processor": settings.processor,
            "queue_depth": queue.depth,
            "frames_dropped": queue.dropped,
        }

    return app


app = create_app()
