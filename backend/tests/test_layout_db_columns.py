"""ORM column presence for layout-preserving OCR and translate tables."""

from app.file_ocr.domain.db.models_result import OcrFileMineru, OcrFilePaddleocr
from app.translate.domain.db.models import DocTranslateJob


def test_paddleocr_has_layout_blocks_json() -> None:
    """Paddle OCR page rows store LDM blocks in jsonb."""
    assert "layout_blocks_json" in OcrFilePaddleocr.__table__.columns


def test_mineru_has_layout_blocks_json() -> None:
    """MinerU page rows reserve the same layout columns."""
    assert "layout_blocks_json" in OcrFileMineru.__table__.columns


def test_doc_translate_job_has_layout_snapshot() -> None:
    """Translation jobs persist a layout snapshot for writers and preview."""
    assert "layout_snapshot_json" in DocTranslateJob.__table__.columns
    assert "layout_source" in DocTranslateJob.__table__.columns
