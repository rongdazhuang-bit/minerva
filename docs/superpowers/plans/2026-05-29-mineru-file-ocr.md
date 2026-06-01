# MinerU 文件 OCR（同步 `/file_parse`）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 替换 MinerU OCR 工具配置为自部署 `mineru-api` 16 项参数，并实现同步 `POST /file_parse` 写路径（S3 → HTTP → `ocr_file_mineru`），使 MINERU 任务可被 INIT 扫描执行。

**Architecture:** 镜像 Paddle 三层：`app/ocr/mineru/` 纯 HTTP 客户端 → `mineru_ocr_request.py` 合并 `ocr_config` → `MineruFileStrategy` 编排落库。URL path 推断模式（`/file_parse` 同步，`/tasks` 占位失败）。首期 `layout_blocks_json` 留空。

**Tech Stack:** Python 3 / FastAPI 后端、httpx、Pydantic v2、SQLAlchemy async；React + Ant Design 设置页；pytest。

**Spec:** `docs/superpowers/specs/2026-05-29-mineru-file-ocr-design.md`

---

## File Map

| 文件 | 职责 |
|------|------|
| `backend/app/ocr/mineru/errors.py` | MinerU 客户端异常层次 |
| `backend/app/ocr/mineru/schemas.py` | `FileParseFormOptions`、`MineruHttpResponse` |
| `backend/app/ocr/mineru/client.py` | `post_file_parse` multipart POST |
| `backend/app/file_ocr/service/mineru_ocr_request.py` | `ocr_config` → form dict；URL path 校验 |
| `backend/app/file_ocr/service/mineru_result_parse.py` | ZIP/JSON → `MineruPageResult[]` |
| `backend/app/file_ocr/service/strategies/mineru.py` | 主编排（替换占位） |
| `backend/app/file_ocr/constants.py` | 扫描白名单加 `MINERU` |
| `backend/tests/test_mineru_ocr_request.py` | form 合并单测 |
| `backend/tests/test_mineru_result_parse.py` | ZIP 解析单测 |
| `backend/tests/test_mineru_client.py` | HTTP 客户端 mock 单测 |
| `backend/tests/fixtures/mineru/sample.zip` | 最小 ZIP fixture |
| `frontend/src/features/settings/ocr/mineruParams.ts` | 配置序列化 |
| `frontend/src/features/settings/ocr/PaddleOcrParamsTab.tsx` | MinerU 表单/只读 |
| `frontend/src/i18n/locales/en.json` | 英文 i18n |
| `frontend/src/i18n/locales/zh-CN.json` | 中文 i18n |

**注释：** 新增 Python 类/方法按仓库 `code-comments` skill 写 docstring。

---

### Task 1: MinerU 异常类

**Files:**
- Create: `backend/app/ocr/mineru/errors.py`
- Modify: `backend/app/ocr/mineru/__init__.py`

- [ ] **Step 1: 创建 `errors.py`**

```python
"""Exceptions raised by the MinerU FastAPI HTTP client."""

from __future__ import annotations


class MineruError(Exception):
    """Base class for MinerU client failures."""


class MineruTransportError(MineruError):
    """HTTP failure: non-success status or network error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        url: str | None = None,
        body_snippet: str | None = None,
    ) -> None:
        """Attach optional HTTP context for callers and logs."""
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.body_snippet = body_snippet


class MineruParseError(MineruError):
    """Response body is not a parseable ZIP/JSON MinerU result."""

    def __init__(self, message: str, *, raw_body: str | None = None) -> None:
        """Optionally retain a truncated body for debugging."""
        super().__init__(message)
        self.raw_body = raw_body
```

- [ ] **Step 2: 更新 `__init__.py` 导出**

```python
"""MinerU FastAPI HTTP client package."""

from app.ocr.mineru.client import post_file_parse
from app.ocr.mineru.errors import MineruError
from app.ocr.mineru.errors import MineruParseError
from app.ocr.mineru.errors import MineruTransportError

__all__ = [
    "MineruError",
    "MineruParseError",
    "MineruTransportError",
    "post_file_parse",
]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/ocr/mineru/errors.py backend/app/ocr/mineru/__init__.py
git commit -m "feat(ocr): add MinerU HTTP client error types"
```

---

### Task 2: MinerU Pydantic schemas

**Files:**
- Create: `backend/app/ocr/mineru/schemas.py`

- [ ] **Step 1: 创建 `schemas.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/ocr/mineru/schemas.py
git commit -m "feat(ocr): add MinerU FileParseFormOptions schema"
```

---

### Task 3: `mineru_ocr_request` + 单测

**Files:**
- Create: `backend/app/file_ocr/service/mineru_ocr_request.py`
- Create: `backend/tests/test_mineru_ocr_request.py`

- [ ] **Step 1: 写失败单测**

```python
"""Tests for MinerU form builder from SysOcrTool.ocr_config."""

from __future__ import annotations

import pytest

from app.file_ocr.service.mineru_ocr_request import (
    build_file_parse_form_for_tool,
    resolve_mineru_url_mode,
)
from app.ocr.mineru.schemas import FileParseFormOptions
from app.sys.tool.ocr.domain.db.models import SysOcrTool


def test_resolve_mineru_url_mode_file_parse() -> None:
    """URL ending with /file_parse is sync mode."""
    assert resolve_mineru_url_mode("http://127.0.0.1:8000/file_parse") == "sync"


def test_resolve_mineru_url_mode_tasks() -> None:
    """URL ending with /tasks is async placeholder mode."""
    assert resolve_mineru_url_mode("http://127.0.0.1:8000/tasks") == "async"


def test_build_form_defaults_output_dir() -> None:
    """Empty ocr_config still sends default output_dir=./output."""
    tool = SysOcrTool(
        name="m",
        url="http://127.0.0.1:8000/file_parse",
        ocr_type="MINERU",
        ocr_config=None,
    )
    form = build_file_parse_form_for_tool(tool)
    assert form["output_dir"] == "./output"
    assert form["end_page_id"] == "99999"
    assert form["lang_list"] == ["ch"]


def test_build_form_http_client_requires_server_url() -> None:
    """*-http-client backend without server_url raises ValueError."""
    tool = SysOcrTool(
        name="m",
        url="http://127.0.0.1:8000/file_parse",
        ocr_type="MINERU",
        ocr_config={"backend": "vlm-http-client"},
    )
    with pytest.raises(ValueError, match="server_url"):
        build_file_parse_form_for_tool(tool)
```

- [ ] **Step 2: 运行单测确认 FAIL**

```bash
cd backend
pytest tests/test_mineru_ocr_request.py -v
```

Expected: `ModuleNotFoundError` 或 import error

- [ ] **Step 3: 实现 `mineru_ocr_request.py`**

```python
"""Build MinerU ``POST /file_parse`` multipart form from ``SysOcrTool.ocr_config``."""

from __future__ import annotations

import json
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import ValidationError

from app.ocr.mineru.schemas import FileParseFormOptions
from app.sys.tool.ocr.domain.db.models import SysOcrTool
from app.sys.tool.ocr.service.ocr_tool_service import normalize_ocr_config_from_db

MineruUrlMode = Literal["sync", "async", "invalid"]


def resolve_mineru_url_mode(url: str) -> MineruUrlMode:
    """Infer sync/async from the configured full URL path."""
    path = urlparse(url.strip()).path.rstrip("/").lower()
    if path.endswith("/file_parse"):
        return "sync"
    if path.endswith("/tasks"):
        return "async"
    return "invalid"


def _ocr_config_dict(tool: SysOcrTool) -> dict[str, Any]:
    """Parse ``SysOcrTool.ocr_config`` into a flat dict (mirrors paddle helper)."""
    raw = tool.ocr_config
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        parsed = json.loads(s)
        return dict(parsed) if isinstance(parsed, dict) else {}
    normalized = normalize_ocr_config_from_db(raw)
    return dict(normalized) if normalized else {}


def build_file_parse_form_for_tool(tool: SysOcrTool) -> dict[str, str | list[str]]:
    """Merge persisted MinerU options into multipart form data for ``/file_parse``."""
    payload = _ocr_config_dict(tool)
    try:
        opts = FileParseFormOptions.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"ocr_config fields are not valid for MinerU file_parse: {exc}") from exc
    if opts.backend.endswith("http-client") and not (opts.server_url or "").strip():
        raise ValueError("mineru_missing_server_url")
    return opts.to_form_data()
```

- [ ] **Step 4: 运行单测确认 PASS**

```bash
cd backend
pytest tests/test_mineru_ocr_request.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/file_ocr/service/mineru_ocr_request.py backend/tests/test_mineru_ocr_request.py
git commit -m "feat(ocr): add MinerU ocr_config to form builder"
```

---

### Task 4: ZIP 解析 + fixture + 单测

**Files:**
- Create: `backend/app/file_ocr/service/mineru_result_parse.py`
- Create: `backend/tests/fixtures/mineru/sample.zip`（脚本生成）
- Create: `backend/tests/test_mineru_result_parse.py`

- [ ] **Step 1: 生成最小 ZIP fixture（Python 一次性脚本）**

```python
# 在 backend/ 目录运行: python -c "..."  或临时脚本
import io, json, zipfile
from pathlib import Path
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("demo/demo.md", "# Page0\n\nHello\n\n![](images/p0.png)\n")
    zf.writestr("demo/demo_middle.json", json.dumps({
        "pdf_info": [{"page_idx": 0, "page_size": [595, 842]}]
    }))
    zf.writestr("demo/images/p0.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")
Path("tests/fixtures/mineru/sample.zip").parent.mkdir(parents=True, exist_ok=True)
Path("tests/fixtures/mineru/sample.zip").write_bytes(buf.getvalue())
```

- [ ] **Step 2: 写失败单测**

```python
"""Tests for MinerU ZIP/JSON response parsing."""

from __future__ import annotations

from pathlib import Path

from app.file_ocr.service.mineru_result_parse import parse_mineru_zip_bytes

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mineru" / "sample.zip"


def test_parse_mineru_zip_single_page() -> None:
    """ZIP with middle.json yields one page with markdown and data-uri image."""
    raw = FIXTURE.read_bytes()
    pages = parse_mineru_zip_bytes(raw)
    assert len(pages) == 1
    assert pages[0].page_index == 0
    assert "Hello" in (pages[0].markdown_text or "")
    assert pages[0].page_width == 595
    assert pages[0].page_height == 842
    images = pages[0].markdown_images or {}
    assert "images/p0.png" in images
    assert images["images/p0.png"].startswith("data:image/")
```

- [ ] **Step 3: 运行确认 FAIL**

```bash
cd backend
pytest tests/test_mineru_result_parse.py -v
```

- [ ] **Step 4: 实现 `mineru_result_parse.py`**

核心类型与函数：

```python
@dataclass
class MineruPageResult:
    page_index: int
    markdown_text: str | None
    markdown_images: dict[str, str] | None
    page_width: int | None
    page_height: int | None


def parse_mineru_response(*, body: bytes, content_type: str) -> list[MineruPageResult]:
    """Dispatch ZIP vs JSON by Content-Type."""


def parse_mineru_zip_bytes(data: bytes) -> list[MineruPageResult]:
    """Safe-extract ZIP in memory; locate ``*.md`` + ``*_middle.json``; inline images."""


def _inline_relative_images(md: str, images_dir: dict[str, bytes]) -> tuple[str, dict[str, str]]:
    """Replace ``![](images/...)`` refs with data URIs from ZIP bytes."""
```

实现要点：
- 用 `zipfile` + `PurePosixPath` 防 path traversal（参考 MinerU `safe_extract_zip` 逻辑，内存解压）。
- 找唯一文档目录：含 `.md` 的最浅目录。
- `middle.json` 的 `pdf_info[].page_idx` 决定页序；单页时整份 md 给 `page_index=0`。
- `page_size: [w,h]` → `page_width/page_height`。
- 图片：读 `images/*` bytes → `base64` data URI。

- [ ] **Step 5: 运行单测 PASS**

```bash
cd backend
pytest tests/test_mineru_result_parse.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/file_ocr/service/mineru_result_parse.py backend/tests/test_mineru_result_parse.py backend/tests/fixtures/mineru/sample.zip
git commit -m "feat(ocr): parse MinerU ZIP response into per-page results"
```

---

### Task 5: HTTP 客户端 `post_file_parse`

**Files:**
- Create: `backend/app/ocr/mineru/client.py`
- Create: `backend/tests/test_mineru_client.py`

- [ ] **Step 1: 写 mock 单测**

```python
"""Tests for MinerU HTTP client."""

from __future__ import annotations

import pytest
import httpx
from pytest import MonkeyPatch

from app.ocr.mineru.client import post_file_parse
from app.ocr.mineru.errors import MineruTransportError


@pytest.mark.asyncio
async def test_post_file_parse_success(monkeypatch: MonkeyPatch) -> None:
    """Successful multipart POST returns body bytes and content-type."""
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/zip"}
        content = b"PK\x03\x04"

        @property
        def request(self):
            class R:
                url = "http://127.0.0.1:8000/file_parse"
            return R()

        def is_success(self) -> bool:
            return True

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, files=None, data=None, headers=None):
            captured["url"] = url
            captured["data"] = data
            captured["files"] = files
            return FakeResponse()

    monkeypatch.setattr("app.ocr.mineru.client.httpx.AsyncClient", lambda **kw: FakeClient())
    body, ctype = await post_file_parse(
        "http://127.0.0.1:8000/file_parse",
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        form_data={"output_dir": "./output", "lang_list": ["ch"]},
    )
    assert body.startswith(b"PK")
    assert ctype == "application/zip"
    assert captured["data"]["output_dir"] == "./output"
```

- [ ] **Step 2: 实现 `client.py`**

```python
async def post_file_parse(
    url: str,
    *,
    file_name: str,
    file_bytes: bytes,
    form_data: dict[str, str | list[str]],
    headers: Mapping[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
    timeout: httpx.Timeout | None = None,
) -> tuple[bytes, str]:
    """POST multipart to MinerU ``/file_parse``; return (body_bytes, content_type)."""
```

要点：
- `files=[("files", (file_name, file_bytes, mime))]`，`mimetypes.guess_type`。
- `lang_list` 为 list 时 httpx 需展开为重复 form 键或 tuple list（与 MinerU 服务端一致；list of tuples `(key, value)` per lang）。
- 非 2xx → `MineruTransportError`。
- INFO 日志 redact 文件 bytes（`len=` only）。

- [ ] **Step 3: 运行单测 PASS + Commit**

```bash
cd backend
pytest tests/test_mineru_client.py -v
git add backend/app/ocr/mineru/client.py backend/tests/test_mineru_client.py backend/app/ocr/mineru/__init__.py
git commit -m "feat(ocr): add MinerU post_file_parse HTTP client"
```

---

### Task 6: `MineruFileStrategy` 主编排

**Files:**
- Modify: `backend/app/file_ocr/service/strategies/mineru.py`
- Modify: `backend/app/file_ocr/constants.py`
- Create: `backend/tests/test_mineru_file_strategy.py`

- [ ] **Step 1: 扩展扫描白名单**

```python
# backend/app/file_ocr/constants.py
FILE_OCR_SUPPORTED_SCAN_OCR_TYPES: frozenset[str] = frozenset({"PADDLE_OCR", "MINERU"})
```

- [ ] **Step 2: 写策略单测（mock HTTP + 内存 DB 或 patch）**

测试用例：
1. `/tasks` URL → `NotImplementedError` 且 message 含 `mineru_async_not_implemented`
2. `/file_parse` + mock `post_file_parse` 返回 fixture ZIP → 断言 `ocr_file.status == SUCCESS` 且写入 `OcrFileMineru` 行

参考 `paddle.py` 结构实现 `MineruFileStrategy.process`：

```python
class MineruFileStrategy(FileOcrEngineStrategy):
    ocr_type: ClassVar[str] = "MINERU"

    async def process(self, *, session, ocr_file, tool) -> None:
        url = (tool.url or "").strip()
        mode = resolve_mineru_url_mode(url)
        if mode == "async":
            raise NotImplementedError("file_ocr:mineru_async_not_implemented")
        if mode == "invalid":
            raise ValueError("file_ocr:mineru_invalid_url_path")
        raw = await read_workspace_object_bytes(...)
        form = build_file_parse_form_for_tool(tool)
        headers = build_ocr_tool_http_headers(tool)
        body, ctype = await post_file_parse(url, file_name=..., file_bytes=raw, form_data=form, headers=headers)
        pages = parse_mineru_response(body=body, content_type=ctype)
        page_pngs = rasterize_source_file(raw, file_name=ocr_file.file_name)
        raster_keys = await upload_page_rasters(...)
        await session.execute(delete(OcrFileMineru).where(...))
        # insert rows, layout_blocks_json=None
        ocr_file.page_count = len(pages)
        ocr_file.status = "SUCCESS"
```

- [ ] **Step 3: 运行单测 PASS**

```bash
cd backend
pytest tests/test_mineru_file_strategy.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/file_ocr/service/strategies/mineru.py backend/app/file_ocr/constants.py backend/tests/test_mineru_file_strategy.py
git commit -m "feat(ocr): implement MinerU sync file_parse strategy"
```

---

### Task 7: 前端 `mineruParams.ts`

**Files:**
- Modify: `frontend/src/features/settings/ocr/mineruParams.ts`

- [ ] **Step 1: 全量重写序列化**

常量：

```typescript
export const MINERU_BACKEND_OPTIONS = [
  'pipeline', 'hybrid-auto-engine', 'hybrid-http-client',
  'vlm-auto-engine', 'vlm-http-client',
] as const

export const MINERU_PARSE_METHOD_OPTIONS = ['auto', 'txt', 'ocr'] as const

export const MINERU_LANG_OPTIONS = [
  'ch', 'en', 'korean', 'japan', 'chinese_cht', 'ch_server', 'ch_lite',
] as const

export const MINERU_DEFAULT_OUTPUT_DIR = './output'
```

`defaultMineruFormValues()` 返回全部 16 项默认值（camelCase 表单键 ↔ snake_case 存储键映射，与现有 mineru 文件风格一致：表单用 camelCase，存储 snake_case）。

布尔三态字段：`formulaEnable` ↔ `formula_enable`，等。

`mineruFormValuesToOcrConfig` 始终写入 `output_dir`（默认 `./output`）。

- [ ] **Step 2: 手动验证（可选）**

在浏览器设置页新建 MinerU 工具，保存后 GET detail 确认 `ocr_config` JSON 含 16 键。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/settings/ocr/mineruParams.ts
git commit -m "feat(ui): rewrite MinerU ocr_config params for mineru-api"
```

---

### Task 8: 前端表单 + i18n

**Files:**
- Modify: `frontend/src/features/settings/ocr/PaddleOcrParamsTab.tsx`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh-CN.json`

- [ ] **Step 1: 替换 `MineruOcrParamsFields`**

字段布局（Row/Col）：
- `outputDir` Input，默认 `./output`
- `langList` Select multiple
- `backend` Select
- `parseMethod` Select
- `formulaEnable` / `tableEnable` triBoolSelect
- `serverUrl` Input（`Form.Item` `dependencies={[['mineru','backend']]}` 当 backend 含 `http-client` 时 required）
- 6 个 return_* 布尔 + `responseFormatZip`
- `startPageId` / `endPageId` InputNumber

同步更新 `MineruOcrParamsReadonly` 字段列表。

删除对 `MINERU_EXTRA_FORMAT_OPTIONS`、`MINERU_MODEL_VERSION_OPTIONS` 的 import。

- [ ] **Step 2: 更新 i18n**

替换 `settings.ocrMineru.*` 全部键（删除旧云端参数键，新增 16 项 label + hint 中英文）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/settings/ocr/PaddleOcrParamsTab.tsx frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh-CN.json
git commit -m "feat(ui): MinerU settings form for mineru-api parameters"
```

---

### Task 9: 全量验证 + spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-05-29-mineru-file-ocr-design.md`

- [ ] **Step 1: 运行后端测试**

```bash
cd backend
pytest tests/test_mineru_ocr_request.py tests/test_mineru_result_parse.py tests/test_mineru_client.py tests/test_mineru_file_strategy.py -v
```

Expected: all passed

- [ ] **Step 2: 前端 typecheck（若项目有）**

```bash
cd frontend
npm run build
```

Expected: build success

- [ ] **Step 3: 回填 spec §11 实现对照 + 状态改为「已实现」**

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-29-mineru-file-ocr-design.md
git commit -m "docs: mark MinerU file OCR spec implemented"
```

---

## Spec Coverage Checklist

| Spec § | Task |
|--------|------|
| §4 16 项 ocr_config | Task 3, 7, 8 |
| §3 URL path 推断 | Task 3, 6 |
| §3 `/tasks` 占位 | Task 6 |
| §5 同步流程 | Task 5, 6 |
| §6 ZIP 解析 | Task 4 |
| §6 layout 留空 | Task 6 |
| §7 MINERU 扫描 | Task 6 |
| §8 前端 | Task 7, 8 |
| §10 测试 | Task 3–6, 9 |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-29-mineru-file-ocr.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，Task 间做 review，迭代快  
2. **Inline Execution** — 在本会话按 Task 顺序直接实现，批次间 checkpoint 确认

你想用哪种方式开始实现？
