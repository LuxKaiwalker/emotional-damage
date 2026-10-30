"""Room lifecycle: 4-letter join codes, leaving, and destruction once everyone is gone."""

import asyncio
import string

import pytest

from app.config import Settings
from app.game.engine import GameEngine, GameError
from app.game.hub import ConnectionManager
from app.game.store import CodeExhausted, InMemoryRoomStore, new_id
from app.models import Phase
from tests.conftest import (
    create_room,
    join_room,
    make_client,
    play_one_round,
    state_of,
    wait_for,
)


def _engine(**overrides) -> GameEngine:
    """An engine with no HTTP around it: the rules are testable on their own."""
    return GameEngine(InMemoryRoomStore(), ConnectionManager(), Settings(**overrides))


async def _fill_single_letter_code_space(engine: GameEngine) -> str:
    """Take all 26 one-letter codes, and return the one the first real room got.

    Claims the codes outright instead of calling `create_room` 26 times: allocation
    samples at random, so filling a space that small by sampling would itself depend on
    luck -- which is the one thing a test about exhaustion must not do.
    """
    first, _ = await engine.create_room("alice")
    for letter in string.ascii_uppercase:
        if letter == first.state.join_code:
            continue
        engine.store.create(
            first.state.model_copy(update={"room_id": new_id("r"), "join_code": letter})
        )
    assert engine.store.count() == 26
    return first.state.join_code


# --- join codes ---------------------------------------------------------------


def test_join_code_is_four_letters(client):
    code = create_room(client)["join_code"]
    assert len(code) == 4
    assert set(code) <= set(string.ascii_uppercase), "codes must be letters, read-aloud safe"


def test_join_code_is_case_insensitive(client):
    host = create_room(client)
    guest = join_room(client, host["join_code"].lower(), "bob")
    assert guest["room_id"] == host["room_id"]


def test_join_code_accepted_in_the_body_too(client):
    host = create_room(client)
    res = client.post(
        "/api/rooms/ignored/join", json={"name": "bob", "join_code": host["join_code"]}
    )
    assert res.status_code == 200, res.text
    assert res.json()["room_id"] == host["room_id"]


def test_join_codes_are_unique_across_live_rooms(client):
    codes = [create_room(client, f"host{i}")["join_code"] for i in range(60)]
    assert len(set(codes)) == len(codes)


async def test_a_destroyed_rooms_code_can_be_reused():
    """Codes are a scarce resource; a dead room must not keep holding one."""
    engine = _engine(join_code_length=1)
    store = engine.store
    freed = await _fill_single_letter_code_space(engine)
    with pytest.raises(CodeExhausted):
        store.allocate_join_code(1)

    await engine.destroy_room(store.get_by_code(freed).state.room_id, reason="test")

    assert store.get_by_code(freed) is None
    # One free code in a 26-code space: sample generously rather than relying on luck.
    assert store.allocate_join_code(1, attempts=2000) == freed


async def test_create_room_reports_exhaustion_as_a_server_error():
    engine = _engine(join_code_length=1)
    await _fill_single_letter_code_space(engine)
    with pytest.raises(GameError) as exc:
        await engine.create_room("one too many")
    assert exc.value.status_code == 503


# --- capacity -----------------------------------------------------------------


def test_room_is_full_at_max_players(tmp_path):
    with make_client(tmp_path, max_players_per_room=2) as client:
        host = create_room(client, "alice")
        join_room(client, host["room_id"], "bob")

        res = client.post(f"/api/rooms/{host['room_id']}/join", json={"name": "carol"})
        assert res.status_code == 409
        assert "full" in res.json()["detail"]


def test_joining_after_game_over_is_allowed(tmp_path):
    """The room can be restarted, so a late arrival waits for the next game instead
    of being turned away."""
    with make_client(tmp_path, rounds_per_game=1, round_seconds=1) as client:
        host = create_room(client, "alice")
        room_id = host["room_id"]
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

        wait_for(client, room_id, lambda s: s["phase"] == "game_over")
        guest = join_room(client, room_id, "bob")
        assert guest["player_id"] in state_of(client, room_id)["players"]


# --- leaving ------------------------------------------------------------------


def test_leaving_removes_the_player(client):
    host = create_room(client, "alice")
    guest = join_room(client, host["room_id"], "bob")

    res = client.post(
        f"/api/rooms/{host['room_id']}/leave", params={"player_id": guest["player_id"]}
    )
    assert res.status_code == 200
    assert res.json() == {"status": "left", "room_destroyed": False}
    assert guest["player_id"] not in state_of(client, host["room_id"])["players"]


def test_leaving_twice_is_a_404(client):
    host = create_room(client, "alice")
    guest = join_room(client, host["room_id"], "bob")
    path = f"/api/rooms/{host['room_id']}/leave"

    assert client.post(path, params={"player_id": guest["player_id"]}).status_code == 200
    assert client.post(path, params={"player_id": guest["player_id"]}).status_code == 404


def test_the_host_leaving_hands_the_room_to_someone_else(client):
    host = create_room(client, "alice")
    guest = join_room(client, host["room_id"], "bob")
    room_id = host["room_id"]

    client.post(f"/api/rooms/{room_id}/leave", params={"player_id": host["player_id"]})
    state = state_of(client, room_id)
    assert state["host_id"] == guest["player_id"]

    # And the new host can actually start a game, which is the point of the handoff.
    res = client.post(f"/api/rooms/{room_id}/start", params={"player_id": guest["player_id"]})
    assert res.status_code == 202


def test_the_last_player_leaving_destroys_the_room(client):
    host = create_room(client, "alice")
    guest = join_room(client, host["room_id"], "bob")
    room_id = host["room_id"]
    code = host["join_code"]

    client.post(f"/api/rooms/{room_id}/leave", params={"player_id": guest["player_id"]})
    res = client.post(f"/api/rooms/{room_id}/leave", params={"player_id": host["player_id"]})
    assert res.json() == {"status": "left", "room_destroyed": True}

    assert client.get(f"/api/rooms/{room_id}").status_code == 404
    assert client.get(f"/api/rooms/{code}").status_code == 404


def test_destroying_a_room_stops_its_running_game(client):
    host = create_room(client, "alice")
    room_id = host["room_id"]
    client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})

    wait_for(client, room_id, lambda s: s["phase"] == "round")
    room = client.app.state.store.get(room_id)
    client.post(f"/api/rooms/{room_id}/leave", params={"player_id": host["player_id"]})

    assert room.task.cancelled() or room.task.done()
    assert client.app.state.store.get(room_id) is None


def test_a_leaving_players_submission_leaves_with_them(hit_client, jpeg):
    host = create_room(hit_client, "alice")
    guest = join_room(hit_client, host["room_id"], "bob")
    room_id = host["room_id"]

    play_one_round(hit_client, room_id, [host, guest], jpeg)
    hit_client.post(f"/api/rooms/{room_id}/leave", params={"player_id": guest["player_id"]})

    state = state_of(hit_client, room_id)
    assert guest["player_id"] not in state["round"]["submissions"]
    assert host["player_id"] in state["round"]["submissions"]


# --- the reaper ---------------------------------------------------------------


async def test_an_abandoned_room_is_reaped_after_the_grace_period():
    """A player who closes their tab never calls /leave, so emptiness has to be noticed."""
    engine = _engine(empty_room_grace_seconds=0)
    room, host_id = await engine.create_room("alice")
    room_id = room.state.room_id

    assert await engine.reap_empty_rooms() == 1
    assert engine.store.get(room_id) is None


async def test_a_room_with_someone_connected_is_never_reaped():
    engine = _engine(empty_room_grace_seconds=0)
    room, host_id = await engine.create_room("alice")
    await engine.set_connected(room.state.room_id, host_id, True)

    assert await engine.reap_empty_rooms() == 0
    assert engine.store.get(room.state.room_id) is not None

    # Dropping the socket starts the clock again, and now it is collectable.
    await engine.set_connected(room.state.room_id, host_id, False)
    assert await engine.reap_empty_rooms() == 1


async def test_a_room_is_kept_through_a_reconnect_inside_the_grace_period():
    engine = _engine(empty_room_grace_seconds=30)
    room, host_id = await engine.create_room("alice")
    room_id = room.state.room_id

    await engine.set_connected(room_id, host_id, True)
    await engine.set_connected(room_id, host_id, False)
    assert await engine.reap_empty_rooms() == 0, "a reload must not cost you the room"

    await engine.set_connected(room_id, host_id, True)
    assert room.empty_since is None
    assert engine.store.get(room_id) is not None


async def test_the_reaper_loop_destroys_an_abandoned_room():
    engine = _engine(empty_room_grace_seconds=0, room_reap_interval_seconds=1)
    room, _ = await engine.create_room("alice")

    task = asyncio.create_task(engine.reap_empty_rooms_forever())
    try:
        async with asyncio.timeout(5):
            while engine.store.get(room.state.room_id) is not None:
                await asyncio.sleep(0.05)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_set_connected_tolerates_a_destroyed_room():
    """The socket teardown path runs after the room may already be gone."""
    engine = _engine()
    room, host_id = await engine.create_room("alice")
    room_id = room.state.room_id
    await engine.destroy_room(room_id, reason="test")

    await engine.set_connected(room_id, host_id, False)  # must not raise
    assert engine.store.get(room_id) is None


async def test_leaving_an_unknown_room_is_a_game_error():
    engine = _engine()
    with pytest.raises(GameError) as exc:
        await engine.leave("r_nope", "p_nope")
    assert exc.value.status_code == 404


async def test_a_fresh_room_starts_in_the_lobby():
    engine = _engine()
    room, host_id = await engine.create_room("alice")
    assert room.state.phase is Phase.LOBBY
    assert room.state.host_id == host_id
    assert room.state.game_no == 1
    assert room.state.game_started_at is None
