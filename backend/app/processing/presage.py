"""Facial expression from Presage SmartSpectra: PROCESSOR=presage.

Presage's SDK only ships for Node, and it wants a continuous camera-rate stream rather than
the two JPEGs a second this server receives. So the classifying happens in the SmartSpectra
sidecar (frontend/src/smart-spectra/server.js), which already gets every player's raw
camera feed: it runs an EXPRESSIONS session per player and pushes each reading here over
loopback (POST /internal/presage/expressions, see app/api/presage.py). This processor then
judges a frame by the newest reading for the player who sent it.

The uploaded JPEG still drives the submission -- rate limit, capture time, placement,
replay. Only the verdict comes from Presage instead of from the frame's bytes.
"""

import time
from dataclasses import dataclass

from app.config import get_settings
from app.game.prompts import TARGET_LABELS, family
from app.models import ProcessResult
from app.processing.base import Processor, RoundCtx

# Never equal to a round target, so it scores nothing. Same sentinel as the Gemini judge.
NO_FACE = "none"

# Presage's ExpressionType, lowercased, to the game's own vocabulary. Neutral is a read,
# just not one any round asks for.
PRESAGE_TO_LABEL = {
    "angry": "angry",
    "contempt": "contempt",
    "disgust": "disgusted",
    "fear": "scared",
    "happy": "happy",
    "neutral": "neutral",
    "sad": "sad",
    "surprise": "surprised",
}
PRESAGE_EXPRESSIONS = tuple(PRESAGE_TO_LABEL)

# Targets Presage has no class for, and the read that stands in for them. Without this a
# "look disappointed" round could never be won.
STAND_INS = {"disappointed": "sad"}

assert set(TARGET_LABELS) <= set(PRESAGE_TO_LABEL.values()) | set(STAND_INS), (
    "a prompt target has no Presage expression that can reach it"
)

# A stand-in makes two targets the same face: `disappointed` is read off `sad`, so one
# held sad face satisfies both. The blitz sequence has to know that or it would put them
# next to each other and hand out a free pass -- so `prompts.INDISTINGUISHABLE` must
# cover every stand-in. Checked here, where the stand-ins are declared, because prompts
# cannot import this module.
assert all(
    stood_in_for in family(reads_as)
    for stood_in_for, reads_as in STAND_INS.items()
), "a Presage stand-in is missing from prompts.INDISTINGUISHABLE; see build_sequence"


@dataclass(frozen=True)
class Reading:
    # Presage expression name -> confidence in [0, 1].
    scores: dict[str, float]
    # Presage's own flag for a read it considers settled.
    stable: bool
    received_at: float  # time.monotonic()


class ExpressionBoard:
    """Newest Presage reading per player, written by the sidecar and read per frame."""

    def __init__(self, forget_after_s: float = 60.0) -> None:
        self._readings: dict[tuple[str, str], Reading] = {}
        self._forget_after_s = forget_after_s

    def put(self, room_id: str, player_id: str, scores: dict[str, float], stable: bool) -> None:
        now = time.monotonic()
        # Readings arrive several times a second per player, so pruning here keeps the
        # board bounded without a reaper task of its own.
        self._readings = {
            key: r
            for key, r in self._readings.items()
            if now - r.received_at < self._forget_after_s
        }
        self._readings[(room_id, player_id)] = Reading(scores, stable, now)

    def latest(self, room_id: str, player_id: str) -> Reading | None:
        return self._readings.get((room_id, player_id))

    def fresh(self, max_age_s: float) -> int:
        """Players whose newest reading is recent enough to score a frame."""
        now = time.monotonic()
        return sum(1 for r in self._readings.values() if now - r.received_at <= max_age_s)

    def clear(self) -> None:
        self._readings.clear()

    def __len__(self) -> int:
        return len(self._readings)


# One per process, like the game state itself: the ingest route writes it and the frame
# workers read it, and both live in the single uvicorn worker.
READINGS = ExpressionBoard()


def judge(reading: Reading, target: str) -> tuple[str, float]:
    """The game label for a reading, and Presage's confidence in it."""
    top, confidence = max(reading.scores.items(), key=lambda kv: kv[1])
    if STAND_INS.get(target) == top:
        return target, confidence
    return PRESAGE_TO_LABEL.get(top, NO_FACE), confidence


class PresageProcessor(Processor):
    """Labels a frame with the player's latest Presage expression."""

    name = "presage"

    def __init__(self, board: ExpressionBoard = READINGS, max_age_s: float | None = None) -> None:
        self._board = board
        self._max_age_s = (
            max_age_s if max_age_s is not None else get_settings().presage_max_age_ms / 1000
        )

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        meta = {
            "processor": self.name,
            "frame_bytes": len(frame),
            "prompt": ctx.prompt,
            "target": ctx.target,
        }

        reading = self._board.latest(ctx.room_id, ctx.player_id)
        age_s = None if reading is None else time.monotonic() - reading.received_at
        if reading is None or age_s > self._max_age_s:
            # No face in view, the sidecar is down, or the player's browser never reached
            # it. Settle the frame as a miss rather than failing it: the next one may land.
            reason = "no_reading" if reading is None else "stale_reading"
            return ProcessResult(score=0.0, label="--", confidence=0.0, meta={**meta, "reason": reason})

        return result_for(reading, ctx.target, {**meta, "reading_age_ms": round(age_s * 1000)})


def result_for(reading: Reading, target: str, meta: dict) -> ProcessResult:
    """The verdict on a reading, shaped like any processor's."""
    label, confidence = judge(reading, target)
    return ProcessResult(
        # `score` is the raw read the UI shows; the point itself comes from the label.
        score=round(confidence * 10, 2),
        label=label,
        confidence=round(confidence, 3),
        meta={
            **meta,
            "stable": reading.stable,
            "scores": {k: round(v, 3) for k, v in reading.scores.items()},
        },
    )
