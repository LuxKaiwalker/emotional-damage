from app.processing.base import Processor
from app.processing.custom import CustomProcessor
from app.processing.dummy import DummyProcessor

_PROCESSORS: dict[str, type[Processor]] = {
    DummyProcessor.name: DummyProcessor,
    CustomProcessor.name: CustomProcessor,
}


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
        return _PROCESSORS[name]()
    except KeyError:
        raise ValueError(f"unknown processor {name!r} (known: {', '.join(known())})") from None
