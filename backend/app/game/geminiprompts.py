"""Extends prompts.py: group prompts by emotion and have Gemini write the spoken line for each.

The message is meant for voicegen.py, so it carries ElevenLabs v3 audio tags ([angry], [whispers], ...).
Run directly:  python app/game/geminiprompts.py   (from backend/)
"""

import os
import random
import sys
from collections import defaultdict
from pathlib import Path

from google import genai
from google.genai import types

# Make `app.*` importable when this file is run as a script from anywhere.
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.game.prompts import Prompt, grab_all_prompts  # noqa: E402

# --- constants: change these freely --------------------------------------
API_KEY_ENV_VAR = "GEMINI_API_KEY"
GEMINI_MODEL = "gemini-2.5-flash"  # best model with a free API tier; swap here if a better free one appears
TEMPERATURE = 1.2  # high on purpose: more unhinged, less repetitive lines
MAX_OUTPUT_TOKENS = 400  # safety cap; lines are one short sentence, so this is never the limit in practice
THINKING_BUDGET = 0  # 2.5 models spend this budget from MAX_OUTPUT_TOKENS, which truncated replies to a word

SYSTEM_PROMPT = """\
You write the voice-over line for a party game where players must pull a specific emotion on their face \
while a camera judges them.

You are given one emotion plus example prompts for it. Write ONE short spoken sentence (a complete \
sentence of 5-10 words, never a single word or phrase) that:
- is funny and meme-y, built around a short, relatable, embarrassing or absurd situation the player is \
supposedly in right now
- makes it unmistakably clear the player should show that emotion on their face right now
- is delivered in an over-the-top voice that matches the emotion

### STYLE ###
- Think classic internet meme captions and "it's over for me" moments: small everyday disasters, awkward \
social situations, petty betrayals, and dramatic overreactions to minor problems.
- Put the player IN the situation (use "you" or first-person framing). Make it specific, but not so \
specific that it gets weird.
- Keep the slang light and generic ("bro", "literally", "it's over", "not again", "the audacity"). \
Do NOT use trendy brainrot terms or niche meme names. No Italian brainrot, 6-7, skibidi, rizz, gyatt, \
sigma, Ohio, and so on.
- The humor comes from the situation and the dramatic delivery, not from stacked slang.
- Don't reuse the same scenario twice. Vary the setting: school, work, dating, family, gym, food, \
phones, public transport, group chats, sleep, shopping, and so on.

### SITUATION EXAMPLES (for flavor only, never copy these) ###
- Walking confidently into a glass door while your crush watches.
- Replying "you too" when the waiter says enjoy your meal.
- Sending a screenshot of the group chat into the group chat.
- Your phone hitting 1% right as the Uber is arriving.
- Waving back at someone who was waving at the person behind you.
- Biting into what you thought was a chocolate cookie but it's raisin.
- Realizing the mic was on the whole time.

Put ElevenLabs v3 audio tags in square brackets before or inside the line to direct the delivery, \
e.g. [angry], [sad], [scared], [surprised], [disgusted], [sarcastic], [whispers], [shouts], [sighs], \
[gasps], [laughs]. Use 1-3 tags that fit the emotion. Tags are the only thing allowed in brackets.

Example (for sad): [sighs] Bro, your rizz just died, so show me sad.

Output only the line itself: no quotes, no explanation, no markdown, no emoji.\
"""


def load_env(path: Path = BACKEND_DIR / ".env") -> None:
    """Minimal .env reader so we don't need python-dotenv. Real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.split(" #")[0].strip().strip("\"'"))


def prompts_by_emotion() -> dict[str, list[str]]:
    """Group every prompt text under its emotion (the Prompt's `target`)."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for p in grab_all_prompts():
        grouped[p.target].append(p.text)
    return dict(grouped)


def generate_message(emotion: str, examples: list[str] | None = None) -> str:
    """Ask Gemini for a tagged, brainrotted voice line that tells players to show `emotion`."""
    load_env()
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(f"{API_KEY_ENV_VAR} is not set (expected in backend/.env)")

    if examples is None:
        examples = prompts_by_emotion().get(emotion, [])
    # The user turn only carries the emotion and examples; tone and format rules live in SYSTEM_PROMPT.
    contents = f"Emotion: {emotion}\nExample prompts for this emotion:\n" + "\n".join(f"- {e}" for e in examples)

    # Keep a reference to the client: if it's garbage-collected mid-call the SDK closes its HTTP session.
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
        ),
    )
    text = (response.text or "").strip()
    if not text:  # response.text is None when the reply is blocked or empty
        raise RuntimeError(f"Gemini returned no text for emotion {emotion!r}")
    return text


def generate_for_prompt(prompt: Prompt) -> str:
    """Generate the voice line for a prompt, using all prompts of the same emotion as context."""
    return generate_message(prompt.target, prompts_by_emotion().get(prompt.target))


if __name__ == "__main__":
    emotion = random.choice(list(prompts_by_emotion()))
    print(f"emotion: {emotion}")
    print(f"message: {generate_message(emotion)}")
