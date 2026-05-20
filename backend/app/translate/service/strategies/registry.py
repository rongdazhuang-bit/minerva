"""Registry mapping file extensions to document translation strategy singletons."""

from __future__ import annotations

from app.translate.service.strategies.base import DocTranslateFormatStrategy
from app.translate.service.strategies.csv_strategy import CsvTranslateStrategy
from app.translate.service.strategies.word_strategy import WordTranslateStrategy
from app.translate.service.strategies.xls_strategy import XlsTranslateStrategy
from app.translate.service.strategies.md_strategy import MdTranslateStrategy
from app.translate.service.strategies.pdf_strategy import PdfTranslateStrategy
from app.translate.service.strategies.txt_strategy import TxtTranslateStrategy
from app.translate.service.strategies.xlsx_strategy import XlsxTranslateStrategy

_REGISTRY: dict[str, DocTranslateFormatStrategy] = {}
for _strategy in (
    TxtTranslateStrategy(),
    MdTranslateStrategy(),
    CsvTranslateStrategy(),
    XlsxTranslateStrategy(),
    XlsTranslateStrategy(),
    WordTranslateStrategy(),
    PdfTranslateStrategy(),
):
    for _ext in _strategy.extensions:
        _REGISTRY[_ext] = _strategy


def get_doc_translate_strategy(ext: str) -> DocTranslateFormatStrategy:
    """Resolve a strategy for a normalized lowercase extension."""

    key = ext.lower().lstrip(".")
    strategy = _REGISTRY.get(key)
    if strategy is None:
        raise KeyError(f"Unknown document translate extension: {ext}")
    return strategy
