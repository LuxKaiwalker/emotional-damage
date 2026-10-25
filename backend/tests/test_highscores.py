"""High scores: each browser's best final score, recorded by the server at game over."""

import asyncio

from app.game.highscores import HighScoreStore
from tests.conftest import make_client, play_one_round, wait_for

ALICE = "browser-alice-1234"
BOB = "browser-bob-5678"


def _create(client, name, client_id):
    res = client.post("/api/rooms", json={"name": name, "client_id": client_id})
    assert res.status_code == 201, res.text
    return res.json()


def _join(client, room_id, name, client_id):
    res = client.post(f"/api/rooms/{room_id}/join", json={"name": name, "client_id": client_id})
    assert res.status_code == 200, res.text
    return res.json()


def _high(client, client_id):
    res = client.get(f"/api/highscores/{client_id}")
    assert res.status_code == 200, res.text
    return res.json()


def test_a_finished_game_records_every_players_final_score(tmp_path, jpeg):
    with make_client(tmp_path, processor="test-hit") as client:
        host = _create(client, "alice", ALICE)
        guest = _join(client, host["room_id"], "bob", BOB)
        play_one_round(client, host["room_id"], [host], jpeg)
        final = wait_for(client, host["room_id"], lambda s: s["phase"] == "game_over")

        alice = _high(client, ALICE)
        assert alice["best"] == final["players"][host["player_id"]]["points"] > 0
        assert alice["best_name"] == "alice" and alice["games_played"] == 1
        assert _high(client, BOB)["best"] == final["players"][guest["player_id"]]["points"]


def test_the_best_game_is_kept_and_every_game_counted(tmp_path, jpeg):
    with make_client(tmp_path, processor="test-hit") as client:
        host = _create(client, "alice", ALICE)
        room_id = host["room_id"]
        play_one_round(client, room_id, [host], jpeg)
        best = wait_for(client, room_id, lambda s: s["phase"] == "game_over")
        best_points = best["players"][host["player_id"]]["points"]

        # Second game: start it and send nothing, so it ends on zero points.
        client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(client, room_id, lambda s: s["phase"] == "game_over" and s["game_no"] == 2)

        alice = _high(client, ALICE)
        assert alice["best"] == best_points
        assert alice["games_played"] == 2


def test_unknown_browser_has_no_high_score_yet(tmp_path):
    with make_client(tmp_path) as client:
        assert _high(client, "never-played-0000") == {
            "best": None, "best_name": None, "best_at": None, "games_played": 0,
        }
        assert client.get("/api/highscores/bad id!").status_code == 422


def test_client_id_is_never_sent_to_other_players(tmp_path):
    with make_client(tmp_path) as client:
        host = _create(client, "alice", ALICE)
        state = client.get(f"/api/rooms/{host['room_id']}").json()
        assert "client_id" not in state["players"][host["player_id"]]
        assert ALICE not in str(host)


def test_scores_survive_a_restart_of_the_server(tmp_path):
    path = tmp_path / "scores.json"
    asyncio.run(HighScoreStore(path).record([(ALICE, "alice", 300)]))
    reloaded = HighScoreStore(path).get(ALICE)
    assert reloaded is not None and reloaded.best == 300 and reloaded.games_played == 1


def test_a_corrupt_file_starts_empty_instead_of_crashing(tmp_path):
    path = tmp_path / "scores.json"
    path.write_text("{not json")
    assert HighScoreStore(path).get(ALICE) is None

def test_blitz_bests_are_filed_apart_from_classic():
    """The two modes do not score on the same scale.

    A blitz total runs into the thousands where a classic game caps at 2000, so a single
    key would let one blitz permanently bury a browser's real classic best.
    """
    from app.game.highscores import HighScoreStore
    from app.models import GameMode

    assert HighScoreStore.key("abc") == "abc", "classic keeps the bare id, so old bests count"
    assert HighScoreStore.key("abc", GameMode.CLASSIC) == "abc"
    assert HighScoreStore.key("abc", GameMode.BLITZ) == "abc:blitz"


async def test_a_blitz_does_not_overwrite_a_classic_best(tmp_path):
    from app.game.highscores import HighScoreStore
    from app.models import GameMode

    store = HighScoreStore(tmp_path / "highscores.json")
    await store.record([("browser", "ace", 1800)])
    await store.record([("browser", "ace", 4200)], GameMode.BLITZ)

    classic = store.get("browser")
    blitz = store.get(HighScoreStore.key("browser", GameMode.BLITZ))
    assert classic is not None and classic.best == 1800
    assert blitz is not None and blitz.best == 4200

