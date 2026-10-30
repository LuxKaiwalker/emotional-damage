"""Each browser's best final score, kept across games, rooms and server restarts.

There are no accounts: a player is a seat in one room. What ties games together is the
`client_id` the browser mints once and sends with every create/join. Scores are written
by the server at game over, never by a client, so nobody can post themselves a high score.

One JSON file is plenty for this: a write happens once per player per game. To run more
than one backend process, move this next to the room store (Redis, a table) -- see store.py.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.models import GameMode, HighScore, utcnow

# The game the landing page's high score means: five-round classic, the default a new
# room plays. Scores from any other shape of game are filed under their own key so the
# headline number always compares like with like -- see `HighScoreStore.key`.
HEADLINE_ROUNDS = 5

log = logging.getLogger(__name__)


class _File(BaseModel):
    scores: dict[str, HighScore] = {}


class HighScoreStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._scores = self._load()

    def _load(self) -> dict[str, HighScore]:
        try:
            return _File.model_validate_json(self.path.read_bytes()).scores
        except FileNotFoundError:
            return {}
        except (OSError, ValidationError):
            # A corrupt file must not take the game server down with it; start over, loudly.
            log.exception("could not read high scores from %s; starting empty", self.path)
            return {}

    def get(self, client_id: str) -> HighScore | None:
        return self._scores.get(client_id)

    @staticmethod
    def key(
        client_id: str,
        mode: GameMode = GameMode.CLASSIC,
        rounds: int = HEADLINE_ROUNDS,
    ) -> str:
        """Where one browser's best for one *kind* of game is filed.

        Namespaced because the kinds do not score on one scale, and a shared key makes the
        number meaningless: a ten-round classic game is worth twice a five-round one, and a
        blitz total runs to a few thousand. Lumping them together lets the longest game a
        browser ever played bury the score it actually set at the game everyone else plays.

        Five-round classic -- the default, and what the landing page shows -- keeps the
        bare `client_id`, so every score recorded before this existed still counts as what
        it already was.
        """
        if mode is not GameMode.CLASSIC:
            return f"{client_id}:{mode.value}"
        return client_id if rounds == HEADLINE_ROUNDS else f"{client_id}:classic{rounds}"

    async def record(
        self,
        finals: list[tuple[str, str, int]],
        mode: GameMode = GameMode.CLASSIC,
        rounds: int = HEADLINE_ROUNDS,
    ) -> None:
        """Count one finished game for each `(client_id, name, points)`, keeping the best."""
        if not finals:
            return
        async with self._lock:
            now = utcnow()
            for raw_id, name, points in finals:
                client_id = self.key(raw_id, mode, rounds)
                prev = self._scores.get(client_id)
                if prev is None:
                    self._scores[client_id] = HighScore(
                        best=points, best_name=name, best_at=now, games_played=1
                    )
                elif points > prev.best:
                    self._scores[client_id] = HighScore(
                        best=points, best_name=name, best_at=now, games_played=prev.games_played + 1
                    )
                else:
                    prev.games_played += 1
            payload = _File(scores=self._scores).model_dump_json()
            await asyncio.to_thread(self._write, payload)

    def _write(self, payload: str) -> None:
        # Write-then-rename, so a crash mid-write leaves the previous file intact.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(payload)
        os.replace(tmp, self.path)
