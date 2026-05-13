"""Registry mapping ``ocr_file.ocr_type`` strings to strategy singletons."""

from __future__ import annotations

from app.file_ocr.service.strategies.base import FileOcrEngineStrategy
from app.file_ocr.service.strategies.mineru import MineruFileStrategy
from app.file_ocr.service.strategies.paddle import PaddleOcrFileStrategy

# One immutable dict avoids accidental runtime mutation in workers.
_REGISTRY: dict[str, FileOcrEngineStrategy] = {
    PaddleOcrFileStrategy.ocr_type: PaddleOcrFileStrategy(),
    MineruFileStrategy.ocr_type: MineruFileStrategy(),
}


def get_file_ocr_strategy(ocr_type: str) -> FileOcrEngineStrategy:
    """Resolve a concrete strategy implementation for a persisted ``ocr_type`` value."""

    strategy = _REGISTRY.get(ocr_type)
    if strategy is None:
        raise KeyError(f"Unknown file OCR engine type: {ocr_type}")
    return strategy
