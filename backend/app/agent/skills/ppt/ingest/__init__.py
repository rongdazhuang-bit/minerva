"""Source ingestion for the PPT skill: convert documents to Markdown."""

from app.agent.skills.ppt.ingest.converters import (
    IngestError,
    build_image_manifest,
    convert_file_to_markdown,
    convert_url_to_markdown,
)

__all__ = [
    "IngestError",
    "build_image_manifest",
    "convert_file_to_markdown",
    "convert_url_to_markdown",
]
