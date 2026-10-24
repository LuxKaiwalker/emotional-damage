from app.processing.base import Processor
from app.processing.custom import CustomProcessor
from app.processing.dummy import DummyProcessor

_PROCESSORS: dict[str, type[Processor]] = {
    DummyProcessor.name: DummyProcessor,
    CustomProcessor.name: CustomProcessor,
}


def get_processor(name: str) -> Processor:
    try:
        return _PROCESSORS[name]()
    except KeyError:
        known = ", ".join(sorted(_PROCESSORS))
        raise ValueError(f"unknown processor {name!r} (known: {known})") from None
