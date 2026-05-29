"""Pydantic models for MinerU FastAPI multipart form options."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FileParseFormOptions(BaseModel):
    """MinerU ``POST /file_parse`` form fields (excluding runtime ``files`` upload)."""

    model_config = ConfigDict(extra="ignore")

    output_dir: str = Field(default="./output")
    lang_list: list[str] = Field(default_factory=lambda: ["ch"])
    backend: str = Field(default="hybrid-auto-engine")
    parse_method: str = Field(default="auto")
    formula_enable: bool = Field(default=True)
    table_enable: bool = Field(default=True)
    server_url: str | None = None
    return_md: bool = Field(default=True)
    return_middle_json: bool = Field(default=True)
    return_model_output: bool = Field(default=False)
    return_content_list: bool = Field(default=False)
    return_images: bool = Field(default=True)
    response_format_zip: bool = Field(default=True)
    start_page_id: int = Field(default=0, ge=0)
    end_page_id: int | None = None

    def to_form_data(self) -> dict[str, str | list[str]]:
        """Serialize to multipart form values (bools as lowercase strings)."""
        langs = [x.strip() for x in self.lang_list if isinstance(x, str) and x.strip()]
        if not langs:
            langs = ["ch"]
        data: dict[str, str | list[str]] = {
            "output_dir": self.output_dir.strip() or "./output",
            "lang_list": langs,
            "backend": self.backend.strip(),
            "parse_method": self.parse_method.strip(),
            "formula_enable": str(self.formula_enable).lower(),
            "table_enable": str(self.table_enable).lower(),
            "return_md": str(self.return_md).lower(),
            "return_middle_json": str(self.return_middle_json).lower(),
            "return_model_output": str(self.return_model_output).lower(),
            "return_content_list": str(self.return_content_list).lower(),
            "return_images": str(self.return_images).lower(),
            "response_format_zip": str(self.response_format_zip).lower(),
            "start_page_id": str(self.start_page_id),
            "end_page_id": str(99999 if self.end_page_id is None else self.end_page_id),
        }
        if self.server_url and self.server_url.strip():
            data["server_url"] = self.server_url.strip()
        return data
