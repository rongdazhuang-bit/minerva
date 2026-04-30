"""Request/response schemas for file OCR APIs."""

from pydantic import BaseModel, Field


class OcrFileOverviewStatsOut(BaseModel):
    """Grouped OCR file-task counters displayed in workspace overview cards."""

    init_count: int = Field(ge=0)
    process_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
