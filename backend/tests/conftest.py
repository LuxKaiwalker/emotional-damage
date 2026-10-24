import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# A real 8x8 JPEG, generated once with PIL. The dummy processor only hashes bytes,
# but keeping the fixture a valid image means a real processor can be dropped in
# without touching the tests.
TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8l"
    "JCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIo"
    "Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAAR"
    "CAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA"
    "AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkK"
    "FhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG"
    "h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl"
    "5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk"
    "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOE"
    "hYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCSiiivojxj/9k="
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        round_seconds=2,
        rounds_per_game=2,
        intermission_seconds=0,
        min_frame_interval_ms=0,
        media_dir=tmp_path / "media",
        processor="dummy",
        worker_count=2,
        queue_maxsize=8,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def jpeg() -> bytes:
    return TINY_JPEG


def frame_files(data: bytes) -> dict:
    return {"file": ("frame.jpg", data, "image/jpeg")}


def create_room(client: TestClient, name: str = "host") -> dict:
    res = client.post("/api/rooms", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def join_room(client: TestClient, room_id: str, name: str) -> dict:
    res = client.post(f"/api/rooms/{room_id}/join", json={"name": name})
    assert res.status_code == 200, res.text
    return res.json()
