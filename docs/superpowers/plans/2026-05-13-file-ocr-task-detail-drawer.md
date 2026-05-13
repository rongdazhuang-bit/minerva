# 文件 OCR「查看详情」抽屉实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为工作区文件 OCR 任务列表实现「查看详情」：仅 `SUCCESS` 可点，以宽度 80% 的 Drawer 拉取 `GET /workspaces/{wid}/ocr-files/{id}/markdown-pages`，按 `ocr_type` 只读策略查询结果表、`page_index` 升序，前端对 `images` 做占位符替换后用 Markdown 渲染。

**Architecture:** 后端在 `app/file_ocr` 内新增 **只读策略注册表**（与写策略 `strategies/registry.py` 分离，避免混淆），路由只做鉴权与调用 **service 层**组装 Pydantic 响应；`markdown_images` 的 JSON 解析与非法 JSON 降级在 service 完成。前端将 **纯函数** `applyOcrMarkdownImagePlaceholders` 置于独立模块并用 **Vitest** 覆盖；`FileOcrTaskPage` 内用 `Drawer` + `ReactMarkdown`/`remarkGfm`，`AbortController` 在关闭抽屉时取消请求。

**Tech Stack:** FastAPI、SQLAlchemy 2 async、Pydantic v2、pytest+httpx；React 18、Ant Design 6、react-markdown 10、remark-gfm、Vitest 3、TypeScript 5.6。

**规格来源:** `docs/superpowers/specs/2026-05-13-file-ocr-task-detail-drawer-design.md`

**注释规范:** 新增 Python/TypeScript 公共 API 须遵守仓库 `d:\ityeahProjects\minerva\.cursor\skills\code-comments\SKILL.md`（类/方法注释等）。

---

## 文件结构总览

| 路径 | 职责 |
|------|------|
| `backend/app/file_ocr/api/schemas.py` | 新增 `OcrFileMarkdownPageOut`、`OcrFileMarkdownPagesOut` |
| `backend/app/file_ocr/service/result_read/base.py` | 只读策略 ABC + `RawOcrResultPage` 数据载体 |
| `backend/app/file_ocr/service/result_read/paddle.py` | `PADDLE_OCR` → 查询 `OcrFilePaddleocr` |
| `backend/app/file_ocr/service/result_read/mineru.py` | `MINERU` → 查询 `OcrFileMineru` |
| `backend/app/file_ocr/service/result_read/registry.py` | `get_file_ocr_result_read_strategy(ocr_type)` |
| `backend/app/file_ocr/service/markdown_pages.py` | 加载 `OcrFile`、状态校验、调策略、解析 JSON、组装响应 |
| `backend/app/file_ocr/api/router.py` | 注册 `GET /{ocr_file_id}/markdown-pages` |
| `backend/tests/test_file_ocr_markdown_pages.py` | 接口与解析行为集成测试 |
| `minerva-ui/src/features/file-ocr/applyOcrMarkdownImagePlaceholders.ts` | 占位符替换纯函数 |
| `minerva-ui/src/features/file-ocr/applyOcrMarkdownImagePlaceholders.test.ts` | Vitest 单测 |
| `minerva-ui/vite.config.ts` | 合并 `test` 配置块 |
| `minerva-ui/package.json` | `devDependencies` 增加 `vitest`，`scripts` 增加 `test` |
| `minerva-ui/src/api/ocrTask.ts` | `getOcrFileMarkdownPages` + 类型 |
| `minerva-ui/src/features/file-ocr/FileOcrTaskPage.tsx` | Drawer、加载态、禁用查看按钮、Markdown 区 |
| `minerva-ui/src/features/file-ocr/FileOcrTaskMarkdown.css`（可选） | Markdown 正文排版（可复用 `RulesManagementPage.css` 片段） |
| `minerva-ui/src/i18n/locales/zh-CN.json`、`en.json` | 抽屉标题、空态、错误码文案 |

---

### Task 1: Pydantic 响应模型

**Files:**
- Modify: `backend/app/file_ocr/api/schemas.py`

- [ ] **Step 1: 在 `schemas.py` 末尾追加模型**

```python
class OcrFileMarkdownPageOut(BaseModel):
    """One OCR result page returned for the task detail drawer."""

    page_index: int | None = None
    markdown_text: str | None = None
    images: dict[str, str] | None = None


class OcrFileMarkdownPagesOut(BaseModel):
    """Full markdown-pages payload for one ``ocr_file`` row."""

    file_id: uuid.UUID
    ocr_type: str
    pages: list[OcrFileMarkdownPageOut]
```

- [ ] **Step 2: 运行静态检查（可选）**

Run: `cd D:\ityeahProjects\minerva\backend && python -m compileall app/file_ocr/api/schemas.py`  
Expected: 无输出即成功。

- [ ] **Step 3: Commit**

```bash
git add backend/app/file_ocr/api/schemas.py
git commit -m "feat(file-ocr): add markdown-pages API schemas"
```

---

### Task 2: 只读策略与注册表

**Files:**
- Create: `backend/app/file_ocr/service/result_read/__init__.py`
- Create: `backend/app/file_ocr/service/result_read/base.py`
- Create: `backend/app/file_ocr/service/result_read/paddle.py`
- Create: `backend/app/file_ocr/service/result_read/mineru.py`
- Create: `backend/app/file_ocr/service/result_read/registry.py`

- [ ] **Step 1: `result_read/__init__.py`**

```python
"""Read-side strategies: map ``ocr_file.ocr_type`` to per-engine result tables."""
```

- [ ] **Step 2: `result_read/base.py`**

```python
"""Abstract read strategy and neutral page row for OCR markdown detail."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RawOcrResultPage:
    """One page row before JSON coercion (``markdown_images`` still raw DB text)."""

    page_index: int | None
    markdown_text: str | None
    markdown_images: str | None


class FileOcrResultReadStrategy(ABC):
    """Loads ordered result rows for a finished ``ocr_file`` from the engine-specific table."""

    ocr_type: ClassVar[str]

    @abstractmethod
    async def load_pages(
        self,
        *,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> list[RawOcrResultPage]:
        """Return pages ordered by ``page_index ASC NULLS LAST`` (SQL-side)."""
```

- [ ] **Step 3: `result_read/paddle.py`**

```python
"""PaddleOCR result read strategy: ``ocr_file_paddleocr``."""

from __future__ import annotations

import uuid
from typing import ClassVar

from sqlalchemy import asc, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.domain.db.models_result import OcrFilePaddleocr

from .base import FileOcrResultReadStrategy, RawOcrResultPage


class PaddleOcrResultReadStrategy(FileOcrResultReadStrategy):
    """Reads per-page markdown from ``ocr_file_paddleocr``."""

    ocr_type: ClassVar[str] = "PADDLE_OCR"

    async def load_pages(
        self,
        *,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> list[RawOcrResultPage]:
        """Select all pages for ``file_id`` in the workspace, ordered by page index."""

        stmt = (
            select(OcrFilePaddleocr)
            .where(
                OcrFilePaddleocr.workspace_id == workspace_id,
                OcrFilePaddleocr.file_id == file_id,
            )
            .order_by(nullslast(asc(OcrFilePaddleocr.page_index)), asc(OcrFilePaddleocr.id))
        )
        rows = (await session.execute(stmt)).scalars().all()
        return [
            RawOcrResultPage(
                page_index=r.page_index,
                markdown_text=r.markdown_text,
                markdown_images=r.markdown_images,
            )
            for r in rows
        ]
```

- [ ] **Step 4: `result_read/mineru.py`**

与 `paddle.py` 对称，将 `OcrFilePaddleocr` 换为 `OcrFileMineru`，`ocr_type: ClassVar[str] = "MINERU"`，`.order_by(nullslast(asc(OcrFileMineru.page_index)), asc(OcrFileMineru.id))`。

- [ ] **Step 5: `result_read/registry.py`**

```python
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
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/file_ocr/service/result_read
git commit -m "feat(file-ocr): add result read strategies for markdown pages"
```

---

### Task 3: Service 组装与 JSON 降级

**Files:**
- Create: `backend/app/file_ocr/service/markdown_pages.py`

- [ ] **Step 1: 实现 `markdown_pages.py`**

要点（实现时写全文件，含模块/函数 docstring）：

1. `import json`、`import logging`、`uuid`。
2. `_LOGGER = logging.getLogger(__name__)`。
3. `def _parse_markdown_images(raw: str | None) -> dict[str, str] | None`：若 `raw` 为 `None` 或空白则 `None`；`try: json.loads(raw)`，若结果为 `dict` 且 **所有键值均为 `str`** 则返回，否则 `_LOGGER.warning` 并返回 `None`；`JSONDecodeError` 同样 `warning` + `None`。
4. `async def get_ocr_file_markdown_pages(*, session, workspace_id, ocr_file_id) -> OcrFileMarkdownPagesOut`：
   - `select(OcrFile).where(OcrFile.id == ocr_file_id, OcrFile.workspace_id == workspace_id)`，`scalar_one_or_none()`。
   - 无行 → `raise AppError("ocr_file.not_found", "OCR task not found", 404)`（与 `router.py` 其它端点一致）。
   - `row.status != "SUCCESS"` → `raise AppError("ocr_file.detail_requires_success", "Task must be SUCCESS to load markdown pages", 409)`。
   - `try: read = get_file_ocr_result_read_strategy(row.ocr_type)`，`except KeyError: raise AppError("ocr_file.unsupported_detail_type", "OCR type does not support markdown detail", 422)`。
   - `raw_pages = await read.load_pages(session=session, workspace_id=workspace_id, file_id=ocr_file_id)`。
   - 构造 `pages=[OcrFileMarkdownPageOut(page_index=p.page_index, markdown_text=p.markdown_text, images=_parse_markdown_images(p.markdown_images)) for p in raw_pages]`。
   - `return OcrFileMarkdownPagesOut(file_id=row.id, ocr_type=row.ocr_type, pages=pages)`。

```python
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.file_ocr.api.schemas import OcrFileMarkdownPageOut, OcrFileMarkdownPagesOut
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.service.result_read.registry import get_file_ocr_result_read_strategy

_LOGGER = logging.getLogger(__name__)


def _parse_markdown_images(raw: str | None) -> dict[str, str] | None:
    """Parse ``markdown_images`` JSON text into a ``str -> str`` map, or ``None`` if invalid."""

    if raw is None or str(raw).strip() == "":
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.warning("markdown_images JSON decode failed for OCR result page")
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, str):
            _LOGGER.warning("markdown_images contains non-string key or value")
            return None
        out[k] = v
    return out if out else None


async def get_ocr_file_markdown_pages(
    *,
    session: AsyncSession,
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
) -> OcrFileMarkdownPagesOut:
    """Load ordered markdown pages for a SUCCESS ``ocr_file`` in the workspace."""

    result = await session.execute(
        select(OcrFile).where(OcrFile.id == ocr_file_id, OcrFile.workspace_id == workspace_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("ocr_file.not_found", "OCR task not found", 404)
    if row.status != "SUCCESS":
        raise AppError(
            "ocr_file.detail_requires_success",
            "Task must be SUCCESS to load markdown pages",
            409,
        )
    try:
        read_strategy = get_file_ocr_result_read_strategy(row.ocr_type)
    except KeyError:
        raise AppError(
            "ocr_file.unsupported_detail_type",
            "OCR type does not support markdown detail",
            422,
        ) from None
    raw_pages = await read_strategy.load_pages(
        session=session, workspace_id=workspace_id, file_id=ocr_file_id
    )
    pages = [
        OcrFileMarkdownPageOut(
            page_index=p.page_index,
            markdown_text=p.markdown_text,
            images=_parse_markdown_images(p.markdown_images),
        )
        for p in raw_pages
    ]
    return OcrFileMarkdownPagesOut(file_id=row.id, ocr_type=row.ocr_type, pages=pages)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/file_ocr/service/markdown_pages.py
git commit -m "feat(file-ocr): add markdown pages service with JSON coercion"
```

---

### Task 4: HTTP 路由

**Files:**
- Modify: `backend/app/file_ocr/api/router.py`

- [ ] **Step 1: 增加 import 与 handler（放在 `delete_ocr_file` 之前或之后均可，保持与 `/{ocr_file_id}/logs` 同风格）**

```python
from app.file_ocr.api.schemas import OcrFileMarkdownPagesOut
from app.file_ocr.service.markdown_pages import get_ocr_file_markdown_pages
```

```python
@file_router.get("/{ocr_file_id}/markdown-pages", response_model=OcrFileMarkdownPagesOut)
async def get_ocr_file_markdown_pages_endpoint(
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileMarkdownPagesOut:
    """Return per-page markdown and parsed image maps for a SUCCESS OCR task."""

    return await get_ocr_file_markdown_pages(
        session=session, workspace_id=workspace_id, ocr_file_id=ocr_file_id
    )
```

- [ ] **Step 2: 运行 `compileall` 或启动 app 冒烟**

Run: `cd D:\ityeahProjects\minerva\backend && python -c "from app.main import app; print('ok')"`  
Expected: 打印 `ok`。

- [ ] **Step 3: Commit**

```bash
git add backend/app/file_ocr/api/router.py
git commit -m "feat(file-ocr): add GET markdown-pages endpoint"
```

---

### Task 5: 后端集成测试

**Files:**
- Create: `backend/tests/test_file_ocr_markdown_pages.py`

- [ ] **Step 1: 编写测试文件**（沿用 `test_file_ocr_api` / `test_file_ocr_scan_init` 的注册+token+`_ensure_ocr_file_columns` 模式；使用 `@pytest.mark.asyncio` + `MINERVA_SKIP_DB_TESTS` 与 `async_session_factory` 插入 `OcrFilePaddleocr` / 非法 JSON 行）。

至少包含以下用例（每个用例独立函数名清晰）：

1. **`test_markdown_pages_success_order_and_images`**：`OcrFile` 置 `SUCCESS`、`PADDLE_OCR`，插入两行 `OcrFilePaddleocr`（`page_index` 为 `1` 与 `0`），`markdown_images` 合法 JSON；`GET .../markdown-pages` 期望 **200**，`pages` 顺序为 **0 先于 1**，第二页 `images` 为解析后的 `dict`。
2. **`test_markdown_pages_invalid_images_json_yields_null_images`**：一行 `markdown_images='not-json'`，期望 **200** 且该页 `images is None`。
3. **`test_markdown_pages_non_success_returns_409`**：`status='INIT'`，期望 **409**，`code == ocr_file.detail_requires_success`（以响应 JSON 为准）。
4. **`test_markdown_pages_not_found_returns_404`**：随机 `ocr_file_id`。
5. **`test_markdown_pages_unknown_ocr_type_returns_422`**：在 DB 中直接 `UPDATE ocr_file SET ocr_type='ZZ'`（若受约束则改用 `async_session_factory` 执行 `UPDATE`；若表有 CHECK 则插入测试专用行时用 raw SQL 跳过约束——以实际 DDL 为准；**若无 CHECK**，`UPDATE` 即可）。

辅助：从 `tests.test_file_ocr_api` 复用 `_ensure_ocr_file_columns`、`_workspace_id_from_access_token` 模式；从 `test_file_ocr_scan_init` 复用 `_db_skip` / `_should_skip_db_tests`。

- [ ] **Step 2: 运行测试**

Run: `cd D:\ityeahProjects\minerva\backend && pytest tests/test_file_ocr_markdown_pages.py -v`  
Expected: 全部 **PASSED**（本地无 Postgres 时 `MINERVA_SKIP_DB_TESTS=1` 应 **skip** 而非 fail）。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_file_ocr_markdown_pages.py
git commit -m "test(file-ocr): cover markdown-pages API"
```

---

### Task 6: 前端占位符纯函数 + Vitest

**Files:**
- Modify: `minerva-ui/package.json`
- Modify: `minerva-ui/vite.config.ts`
- Create: `minerva-ui/src/features/file-ocr/applyOcrMarkdownImagePlaceholders.ts`
- Create: `minerva-ui/src/features/file-ocr/applyOcrMarkdownImagePlaceholders.test.ts`

- [ ] **Step 1: 安装 Vitest**

Run:

```bash
cd D:\ityeahProjects\minerva\minerva-ui
npm install -D vitest@^3.0.0
```

在 `package.json` 的 `scripts` 增加：`"test": "vitest run"`。

- [ ] **Step 2: 更新 `vite.config.ts`**

在现有 `defineConfig` 对象上增加顶层键（保持 `plugins`/`resolve`/`server` 不变）：

```ts
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
```

文件首行增加：`/// <reference types="vitest/config" />`

- [ ] **Step 3: `applyOcrMarkdownImagePlaceholders.ts`**

```typescript
/**
 * Replace OCR engine placeholder substrings in markdown using a ``placeholder -> url`` map.
 *
 * Keys are applied in **descending length** order so shorter keys do not break longer ones.
 */
export function applyOcrMarkdownImagePlaceholders(
  text: string | null | undefined,
  images: Record<string, string> | null | undefined,
): string {
  const base = text ?? ''
  if (images == null || Object.keys(images).length === 0) {
    return base
  }
  const keys = Object.keys(images).sort((a, b) => b.length - a.length)
  let out = base
  for (const k of keys) {
    const val = images[k]
    if (val === undefined) continue
    out = out.split(k).join(val)
  }
  return out
}
```

- [ ] **Step 4: `applyOcrMarkdownImagePlaceholders.test.ts`**

```typescript
import { describe, expect, it } from 'vitest'

import { applyOcrMarkdownImagePlaceholders } from './applyOcrMarkdownImagePlaceholders'

describe('applyOcrMarkdownImagePlaceholders', () => {
  it('returns empty string for null text and no images', () => {
    expect(applyOcrMarkdownImagePlaceholders(null, null)).toBe('')
  })

  it('applies longer keys before shorter keys', () => {
    const text = 'ab X ac'
    const images = { a: '1', ab: '2' }
    expect(applyOcrMarkdownImagePlaceholders(text, images)).toBe('2 X 1c')
  })

  it('leaves text unchanged when images map is empty', () => {
    expect(applyOcrMarkdownImagePlaceholders('hello', {})).toBe('hello')
  })
})
```

- [ ] **Step 5: 运行 Vitest**

Run: `cd D:\ityeahProjects\minerva\minerva-ui && npm run test`  
Expected: **1 test file passed**。

- [ ] **Step 6: Commit**

```bash
git add minerva-ui/package.json minerva-ui/package-lock.json minerva-ui/vite.config.ts minerva-ui/src/features/file-ocr/applyOcrMarkdownImagePlaceholders.ts minerva-ui/src/features/file-ocr/applyOcrMarkdownImagePlaceholders.test.ts
git commit -m "feat(file-ocr-ui): add markdown image placeholder helper and vitest"
```

---

### Task 7: API 客户端类型与请求函数

**Files:**
- Modify: `minerva-ui/src/api/ocrTask.ts`

- [ ] **Step 1: 追加类型与函数**

```typescript
export type OcrFileMarkdownPage = {
  page_index: number | null
  markdown_text: string | null
  images: Record<string, string> | null
}

export type OcrFileMarkdownPages = {
  file_id: string
  ocr_type: string
  pages: OcrFileMarkdownPage[]
}

/** Load per-page markdown and image maps for a SUCCESS OCR task. */
export function getOcrFileMarkdownPages(
  workspaceId: string,
  ocrFileId: string,
  init?: RequestInit,
) {
  return apiJson<OcrFileMarkdownPages>(
    ocrFilePath(workspaceId, `/${ocrFileId}/markdown-pages`),
    init,
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add minerva-ui/src/api/ocrTask.ts
git commit -m "feat(file-ocr-ui): add markdown-pages API client"
```

---

### Task 8: 任务列表页 Drawer 与交互

**Files:**
- Modify: `minerva-ui/src/features/file-ocr/FileOcrTaskPage.tsx`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`
- Optional: `minerva-ui/src/features/file-ocr/FileOcrTaskMarkdown.css` + import

- [ ] **Step 1: 状态与 ref**

在组件内增加：`detailOpen`、`detailTarget: OcrFileListItem | null`、`detailLoading`、`detailError: string | null`、`detailData: OcrFileMarkdownPages | null`，以及 `useRef<AbortController | null>(null)`。

- [ ] **Step 2: `openDetailDrawer(row)`**

仅当 `row.status === 'SUCCESS'` 时：设置 `detailTarget`、`detailOpen true`，清空 `detailError`，`abort` 旧 controller，新建 `AbortController`，`setDetailLoading(true)`，调用 `getOcrFileMarkdownPages(workspaceId, row.id, { signal })`，成功 `setDetailData`，失败根据 `ApiError.code` 映射 i18n（`ocr_file.detail_requires_success`、`ocr_file.unsupported_detail_type` 与通用 `message.error`），`finally` 中 `setDetailLoading(false)`。

- [ ] **Step 3: 关闭抽屉**

`onClose`：`abortController.abort()`，`setDetailOpen(false)`，`detailTarget` 置 `null`，`detailData` 置 `null`。

- [ ] **Step 4: 操作列按钮**

将眼睛按钮改为：`disabled={row.status !== 'SUCCESS'}`，`Tooltip` 在非 SUCCESS 时使用 `title={t('fileOcr.tasks.action.viewDisabledHint')}`（需在 i18n 增加），SUCCESS 时 `title={t('fileOcr.tasks.action.view')}`；`onClick` 调用 `openDetailDrawer(row)`，**移除**对 `onPendingAction('fileOcr.tasks.action.view')` 的调用。

- [ ] **Step 5: Drawer JSX**

- `open={detailOpen}`，`onClose=...`，`width="80%"`，`destroyOnClose`（可选，减少残留状态）。
- `title`：`detailTarget?.file_name ?? t('fileOcr.tasks.detail.titleFallback')`。
- 内容：`detailLoading` → `<Spin />`；`detailError` → `Alert`；否则若 `pages.length===0` → `Empty` 文案；否则对 `pages` 做 `map`：每块先 `##` 标题（`page_index` 为 number 用 `page_index + 1`，否则 `i+1`），再 `ReactMarkdown` + `remarkGfm`，`children` 为 `applyOcrMarkdownImagePlaceholders(page.markdown_text, page.images)`。
- 可选：外层 `div` 加 `className="file-ocr-task-markdown"` 并复制 `RulesManagementPage.css` 中相关规则到新 css 文件。

- [ ] **Step 6: i18n 键（中英文同步）**

示例键：`fileOcr.tasks.detail.empty`、`fileOcr.tasks.detail.loadFailed`、`fileOcr.tasks.action.viewDisabledHint`、`fileOcr.tasks.detail.pageTitle`（若用模板 `{{n}}`）等。

- [ ] **Step 7: Lint 与构建**

Run: `cd D:\ityeahProjects\minerva\minerva-ui && npm run lint && npm run build`  
Expected: **无错误**。

- [ ] **Step 8: Commit**

```bash
git add minerva-ui/src/features/file-ocr/FileOcrTaskPage.tsx minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
# 若新增 css：
# git add minerva-ui/src/features/file-ocr/FileOcrTaskMarkdown.css
git commit -m "feat(file-ocr-ui): markdown detail drawer for SUCCESS tasks"
```

---

## Spec 对照自检（计划作者已完成）

| 规格章节 | 对应 Task |
|----------|-----------|
| 4.1 仅 SUCCESS 可点 | Task 8 |
| 4.2 404 / 409 | Task 3–4；前端 ApiError 提示 Task 8 |
| 4.3 422 未知类型 | Task 3–5 |
| 5.2 响应体 | Task 1、3 |
| 5.3 空 pages | Task 3（天然 `[]`）+ Task 8 Empty |
| 6.1 Drawer 80% | Task 8 |
| 6.2 占位符替换 | Task 6、8 |
| 6.3 页标题 | Task 8 |
| 6.4 加载/错误 | Task 8 |
| 7 只读策略注册 | Task 2–3 |
| 8 测试 | Task 5、6 |

**占位符扫描:** 本计划未使用「TBD / 稍后实现」类措辞；Task 5 中若 DDL 对 `ocr_type` 有 CHECK，实现者应在该任务内将「`UPDATE ... ZZ`」改为等价可落库方案并在提交前跑通 pytest。

---

## 执行交接

**计划已保存到** `docs/superpowers/plans/2026-05-13-file-ocr-task-detail-drawer.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理执行，任务间人工快速验收，迭代快。  
2. **Inline Execution** — 在本会话用 executing-plans 连续执行多步并设检查点。

你更倾向哪一种？
