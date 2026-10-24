import asyncio
import hashlib

from app.game.prompts import TARGET_LABELS
from app.models import ProcessResult
from app.processing.base import Processor, RoundCtx

# Drawn from the game's own vocabulary: a label outside it could never match a round target,
# so a placeholder that invented its own would score zero points forever.
LABELS = TARGET_LABELS


class DummyProcessor(Processor):
    """Deterministic placeholder: same bytes in, same score out.

    Derives a stable pseudo-label from the frame digest so tests can assert on it and the
    UI has something that visibly moves. The label is what the engine scores against the
    round target. Replace with a real model via PROCESSOR=custom.
    """

    name = "dummy"

    def __init__(self, fake_latency_s: float = 0.05) -> None:
        self._fake_latency_s = fake_latency_s

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        # Stand in for model inference time so the async plumbing is actually exercised.
        if self._fake_latency_s:
            await asyncio.sleep(self._fake_latency_s)

        digest = hashlib.sha256(frame).digest()
        score = round(digest[0] / 255 * 10, 2)
        label = LABELS[digest[1] % len(LABELS)]
        confidence = round(0.5 + (digest[2] / 255) * 0.5, 3)

        return ProcessResult(
            score=score,
            label=label,
            confidence=confidence,
            meta={
                "processor": self.name,
                "frame_bytes": len(frame),
                "prompt": ctx.prompt,
                "target": ctx.target,
            },
        )
