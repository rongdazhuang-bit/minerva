"""PaddleOCR-VL serving HTTP client and Pydantic schemas (decoupled from business modules)."""

from app.ocr.paddleocr.client import layout_parsing_body
from app.ocr.paddleocr.client import paddleocr_default_timeout
from app.ocr.paddleocr.client import post_layout_parsing
from app.ocr.paddleocr.client import post_restructure_pages
from app.ocr.paddleocr.client import restructure_pages_body
from app.ocr.paddleocr.errors import PaddleOcrVlApiError
from app.ocr.paddleocr.errors import PaddleOcrVlError
from app.ocr.paddleocr.errors import PaddleOcrVlParseError
from app.ocr.paddleocr.errors import PaddleOcrVlTransportError
from app.ocr.paddleocr.pruned_result import LayoutDetBox
from app.ocr.paddleocr.pruned_result import LayoutDetRes
from app.ocr.paddleocr.pruned_result import ParsingResBlock
from app.ocr.paddleocr.pruned_result import PrunedModelSettings
from app.ocr.paddleocr.pruned_result import PrunedResult
from app.ocr.paddleocr.schemas import LayoutParsingApiResponse
from app.ocr.paddleocr.schemas import LayoutParsingPageResult
from app.ocr.paddleocr.schemas import LayoutParsingRequest
from app.ocr.paddleocr.schemas import LayoutParsingResultPayload
from app.ocr.paddleocr.schemas import MarkdownResult
from app.ocr.paddleocr.schemas import RestructurePageItem
from app.ocr.paddleocr.schemas import RestructurePagesRequest

__all__ = [
    "LayoutDetBox",
    "LayoutDetRes",
    "LayoutParsingApiResponse",
    "LayoutParsingPageResult",
    "LayoutParsingRequest",
    "LayoutParsingResultPayload",
    "MarkdownResult",
    "ParsingResBlock",
    "PrunedModelSettings",
    "PrunedResult",
    "PaddleOcrVlApiError",
    "PaddleOcrVlError",
    "PaddleOcrVlParseError",
    "PaddleOcrVlTransportError",
    "RestructurePageItem",
    "RestructurePagesRequest",
    "layout_parsing_body",
    "paddleocr_default_timeout",
    "post_layout_parsing",
    "post_restructure_pages",
    "restructure_pages_body",
]
