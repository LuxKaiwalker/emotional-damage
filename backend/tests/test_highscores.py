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
    # Five rounds on purpose: that is the game the headline high score is about, and the
    # only shape that lands in its slot. See HighScoreStore.key.
    with make_client(
        tmp_path, processor="test-hit", rounds_per_game=5, round_seconds=1
    ) as client:
        host = _create(client, "alice", ALICE)
        guest = _join(client, host["room_id"], "bob", BOB)
        play_one_round(client, host["room_id"], [host], jpeg)
        final = wait_for(
            client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=30.0
        )

        alice = _high(client, ALICE)
        assert alice["best"] == final["players"][host["player_id"]]["points"] > 0
        assert alice["best_name"] == "alice" and alice["games_played"] == 1
        assert _high(client, BOB)["best"] == final["players"][guest["player_id"]]["points"]


def test_the_best_game_is_kept_and_every_game_counted(tmp_path, jpeg):
    with make_client(
        tmp_path, processor="test-hit", rounds_per_game=5, round_seconds=1
    ) as client:
        host = _create(client, "alice", ALICE)
        room_id = host["room_id"]
        play_one_round(client, room_id, [host], jpeg)
        best = wait_for(
            client, room_id, lambda s: s["phase"] == "game_over", timeout=30.0
        )
        best_points = best["players"][host["player_id"]]["points"]

        # Second game: start it and send nothing, so it ends on zero points.
        client.post(f"/api/rooms/{room_id}/restart", params={"player_id": host["player_id"]})
        client.post(f"/api/rooms/{room_id}/start", params={"player_id": host["player_id"]})
        wait_for(
            client,
            room_id,
            lambda s: s["phase"] == "game_over" and s["game_no"] == 2,
            timeout=30.0,
        )

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

def test_the_headline_key_is_five_round_classic():
    """The landing page shows one number, so it has to mean one kind of game.

    Five-round classic keeps the bare `client_id` on purpose: it is the default a new room
    plays, and it keeps every score recorded before the namespacing existed meaning what it
    already meant.
    """
    from app.game.highscores import HEADLINE_ROUNDS, HighScoreStore
    from app.models import GameMode

    assert HEADLINE_ROUNDS == 5
    assert HighScoreStore.key("abc") == "abc"
    assert HighScoreStore.key("abc", GameMode.CLASSIC, 5) == "abc"


def test_other_kinds_of_game_are_filed_apart():
    """Each shape of game gets its own best, because they are worth different numbers.

    A ten-round classic game is worth twice a five-round one and a blitz runs to a few
    thousand, so one shared key lets the longest game a browser ever played bury the score
    it set at the game the landing page is actually talking about.
    """
    from app.game.highscores import HighScoreStore
    from app.models import GameMode

    assert HighScoreStore.key("abc", GameMode.CLASSIC, 10) == "abc:classic10"
    assert HighScoreStore.key("abc", GameMode.BLITZ) == "abc:blitz"
    assert HighScoreStore.key("abc", GameMode.BLITZ, 10) == "abc:blitz"
    keys = {
        HighScoreStore.key("abc", GameMode.CLASSIC, 5),
        HighScoreStore.key("abc", GameMode.CLASSIC, 10),
        HighScoreStore.key("abc", GameMode.BLITZ),
    }
    assert len(keys) == 3, "every kind needs its own slot"


async def test_a_longer_game_does_not_overwrite_the_headline_best(tmp_path):
    """The case that made the number ambiguous: ten rounds outscoring five."""
    from app.game.highscores import HighScoreStore
    from app.models import GameMode

    store = HighScoreStore(tmp_path / "highscores.json")
    await store.record([("browser", "ace", 900)], GameMode.CLASSIC, 5)
    await store.record([("browser", "ace", 1900)], GameMode.CLASSIC, 10)

    headline = store.get("browser")
    assert headline is not None and headline.best == 900, (
        "a ten-round game must not become the five-round best"
    )
    ten = store.get(HighScoreStore.key("browser", GameMode.CLASSIC, 10))
    assert ten is not None and ten.best == 1900


async def test_a_blitz_does_not_overwrite_the_headline_best(tmp_path):
    from app.game.highscores import HighScoreStore
    from app.models import GameMode

    store = HighScoreStore(tmp_path / "highscores.json")
    await store.record([("browser", "ace", 900)])
    await store.record([("browser", "ace", 4200)], GameMode.BLITZ)

    headline = store.get("browser")
    blitz = store.get(HighScoreStore.key("browser", GameMode.BLITZ))
    assert headline is not None and headline.best == 900
    assert blitz is not None and blitz.best == 4200


async def test_games_played_counts_per_kind(tmp_path):
    """"best of N games" on the badge has to mean N games of *that* kind."""
    from app.game.highscores import HighScoreStore
    from app.models import GameMode

    store = HighScoreStore(tmp_path / "highscores.json")
    await store.record([("browser", "ace", 900)])
    await store.record([("browser", "ace", 400)])
    await store.record([("browser", "ace", 4200)], GameMode.BLITZ)

    assert store.get("browser").games_played == 2
    assert store.get(HighScoreStore.key("browser", GameMode.BLITZ)).games_played == 1


async def test_a_ten_round_game_leaves_the_headline_badge_empty(tmp_path, jpeg):
    """End to end, through the route the landing page actually reads.

    The badge says "5-round classic", so a ten-round game must not put a number behind
    that label -- it goes to its own slot and the badge stays honest about having none.
    """
    with make_client(
        tmp_path, processor="test-hit", rounds_per_game=10, round_seconds=1
    ) as client:
        host = _create(client, "alice", ALICE)
        play_one_round(client, host["room_id"], [host], jpeg)
        wait_for(client, host["room_id"], lambda s: s["phase"] == "game_over", timeout=30.0)

        assert _high(client, ALICE)["best"] is None, (
            "a ten-round game must not show up under the five-round label"
        )
