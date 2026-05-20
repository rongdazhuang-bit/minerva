"""ORM tablename contracts for document translation tables."""

from app.translate.domain.db.models import DocTranslateJob, DocTranslateSegment


def test_doc_translate_job_tablename() -> None:
    assert DocTranslateJob.__tablename__ == "doc_translate_job"


def test_doc_translate_segment_tablename() -> None:
    assert DocTranslateSegment.__tablename__ == "doc_translate_segment"
