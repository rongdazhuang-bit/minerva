"""Registry mapping ``ocr_file.ocr_type`` to markdown read strategy singletons."""

from __future__ import annotations

from app.file_ocr.service.result_read.base import FileOcrResultReadStrategy
from app.file_ocr.service.result_read.mineru import MineruOcrResultReadStrategy
from app.file_ocr.service.result_read.paddle import PaddleOcrResultReadStrategy

_READ_REGISTRY: dict[str, FileOcrResultReadStrategy] = {
    PaddleOcrResultReadStrategy.ocr_type: PaddleOcrResultReadStrategy(),
    MineruOcrResultReadStrategy.ocr_type: MineruOcrResultReadStrategy(),
}


def get_file_ocr_result_read_strategy(ocr_type: str) -> FileOcrResultReadStrategy:
    """Resolve read strategy; raises ``KeyError`` when ``ocr_type`` is unknown."""

    strategy = _READ_REGISTRY.get(ocr_type)
    if strategy is None:
        raise KeyError(ocr_type)
    return strategy

