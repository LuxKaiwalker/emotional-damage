"""Drop your real frame processing in here, then run with PROCESSOR=custom.

Sketch for a blocking model (OpenCV, mediapipe, torch, ...):

    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    _pool = ThreadPoolExecutor(max_workers=2)

    def _infer(frame: bytes) -> tuple[float, str, float]:
        import cv2, numpy as np
        img = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR)
        ...
        return score, label, confidence

    class CustomProcessor:
        name = "custom"

        async def process(self, frame, ctx):
            loop = asyncio.get_running_loop()
            score, label, conf = await loop.run_in_executor(_pool, _infer, frame)
            return ProcessResult(score=score, label=label, confidence=conf)

For a hosted vision model, `await`ing an async HTTP client here is fine -- the worker pool
in app/capture/queue.py already gives you concurrency.
"""

from app.models import ProcessResult
from app.processing.base import Processor, RoundCtx


class CustomProcessor(Processor):
    name = "custom"

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        raise NotImplementedError(
            "PROCESSOR=custom is a stub. Implement CustomProcessor.process in "
            "app/processing/custom.py, or run with PROCESSOR=dummy."
        )
