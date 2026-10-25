from typing import Callable

from app.processing.base import Processor
from app.processing.custom import CustomProcessor
from app.processing.dummy import DummyProcessor

# Name -> zero-arg factory. Factories rather than classes so a processor that needs a
# heavy or optional SDK is only imported when it is the one actually selected: a stale
# virtualenv missing `google-genai` must not stop PROCESSOR=dummy from running.
_PROCESSORS: dict[str, Callable[[], Processor]] = {
    DummyProcessor.name: DummyProcessor,
    CustomProcessor.name: CustomProcessor,
}


def _make_gemini() -> Processor:
    from app.processing.gemini import GeminiProcessor

    return GeminiProcessor()


def _make_presage() -> Processor:
    from app.processing.presage import PresageProcessor

    return PresageProcessor()


_PROCESSORS["gemini"] = _make_gemini
_PROCESSORS["presage"] = _make_presage


def register(processor: type[Processor]) -> None:
    """Add a processor under its own `name`, so `PROCESSOR=<name>` can select it.

    Mostly for tests and experiments: a processor with a known, fixed verdict is the only
    way to assert on scoring, since the real rule is "the label has to match the target".
    """
    _PROCESSORS[processor.name] = processor


def known() -> list[str]:
    return sorted(_PROCESSORS)


def get_processor(name: str) -> Processor:
    try:
        factory = _PROCESSORS[name]
    except KeyError:
        raise ValueError(f"unknown processor {name!r} (known: {', '.join(known())})") from None
    return factory()
