"""Real frame processing: ask Gemini which emotion is on the face in the frame.

Run with PROCESSOR=gemini and GEMINI_API_KEY set.

This is the piece that makes the game actually a game. `dummy` derives a label from the
frame's SHA-256, so identical bytes always produce the same "emotion" and the player's
face is irrelevant; this classifies the real image.

The model is constrained to the game's own vocabulary (`prompts.TARGET_LABELS`) plus
"none". Scoring is `label == round.target`, so a label outside that set could never win a
point -- the enum in the response schema is what keeps the model from inventing one.
"""

import json
import logging

from google import genai
from google.genai import types

from app.config import get_settings
from app.game.prompts import TARGET_LABELS
from app.models import ProcessResult
from app.processing.base import Processor, RoundCtx

log = logging.getLogger(__name__)

# Returned when no face is readable. Never equal to a round target, so it scores nothing.
NO_FACE = "none"

TEMPERATURE = 0.0  # classification, not comedy: we want the same frame judged the same way
MAX_OUTPUT_TOKENS = 200
THINKING_BUDGET = 0  # 2.5 models spend this from MAX_OUTPUT_TOKENS, which truncates replies

SYSTEM_PROMPT = f"""\
You are the judge in a party game. You are given one webcam still of a player who is \
trying to pull a specific facial expression.

Name the single emotion their face is most clearly showing, chosen only from this list:
{", ".join(TARGET_LABELS)}

Rules:
- Judge the face only: ignore the background, lighting, clothing and any text in the image.
- Pick the closest listed emotion even when the expression is exaggerated or hammy; players \
are performing on purpose, so a theatrical face still counts.
- If there is no visible face, it is too dark or blurry to read, or the face is neutral and \
showing none of the listed emotions, answer "{NO_FACE}".
- `confidence` is how sure you are, from 0.0 to 1.0.

Answer with JSON only.\
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "label": {"type": "STRING", "enum": [*TARGET_LABELS, NO_FACE]},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["label", "confidence"],
}


class GeminiProcessor(Processor):
    """Classifies a JPEG into one of the game's target labels."""

    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        api_key = settings.gemini_api_key
        if not api_key:
            # Fail at startup rather than on every frame: a missing key is a config
            # mistake, and 200 failed submissions is a worse way to find out.
            raise ValueError(
                "PROCESSOR=gemini needs GEMINI_API_KEY (environment or backend/.env). "
                "Use PROCESSOR=dummy to run without a model."
            )
        self._model = settings.gemini_vision_model
        # Held for the processor's lifetime: if the client is garbage-collected mid-call
        # the SDK closes its HTTP session underneath the request.
        self._client = genai.Client(api_key=api_key)

    async def process(self, frame: bytes, ctx: RoundCtx) -> ProcessResult:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=frame, mime_type="image/jpeg"),
                # The target is given as context, not as the answer: naming it lets the
                # model resolve a borderline face, and the enum stops it from simply
                # echoing whatever we asked for.
                types.Part.from_text(text=f"This round asked the player to look {ctx.target}."),
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=TEMPERATURE,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
            ),
        )

        text = (response.text or "").strip()
        if not text:
            # Blocked or empty reply. Raising marks the submission failed, which the
            # frame queue already handles; it does not take the round down.
            raise RuntimeError("Gemini returned no text for this frame")

        payload = json.loads(text)
        label = str(payload.get("label") or NO_FACE)
        if label not in TARGET_LABELS and label != NO_FACE:
            # The schema should prevent this; if the model slips, do not let an
            # unknown label through as if it were a real read.
            log.warning("gemini returned off-vocabulary label %r", label)
            label = NO_FACE

        confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))

        return ProcessResult(
            # `score` is the raw read the UI shows; the point itself comes from the label.
            score=round(confidence * 10, 2),
            label=label,
            confidence=round(confidence, 3),
            meta={
                "processor": self.name,
                "model": self._model,
                "frame_bytes": len(frame),
                "prompt": ctx.prompt,
                "target": ctx.target,
            },
        )
