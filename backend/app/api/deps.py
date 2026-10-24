"""Request-scoped access to the singletons created in the app lifespan."""

from typing import Annotated

from fastapi import Depends, Request

from app.capture.media import MediaStore
from app.capture.queue import FrameQueue
from app.config import Settings
from app.game.engine import GameEngine
from app.game.store import InMemoryRoomStore
from app.game.voice import VoiceStore


def get_engine(request: Request) -> GameEngine:
    return request.app.state.engine


def get_frames(request: Request) -> FrameQueue:
    return request.app.state.frames


def get_media(request: Request) -> MediaStore:
    return request.app.state.media


def get_config(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> InMemoryRoomStore:
    return request.app.state.store


def get_voice_store(request: Request) -> VoiceStore:
    return request.app.state.voice_store


EngineDep = Annotated[GameEngine, Depends(get_engine)]
FrameQueueDep = Annotated[FrameQueue, Depends(get_frames)]
MediaDep = Annotated[MediaStore, Depends(get_media)]
SettingsDep = Annotated[Settings, Depends(get_config)]
RoomStoreDep = Annotated[InMemoryRoomStore, Depends(get_store)]
VoiceStoreDep = Annotated[VoiceStore, Depends(get_voice_store)]
