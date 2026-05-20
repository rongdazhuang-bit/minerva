"""Convert legacy Office formats via LibreOffice headless (``.doc`` ↔ ``.docx``)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.exceptions import AppError

log = logging.getLogger(__name__)


def resolve_soffice_executable() -> str | None:
    """Resolve ``soffice`` binary from settings, PATH, or common install locations."""

    custom = (settings.doc_translate_soffice_executable or "").strip()
    if custom and Path(custom).is_file():
        return custom
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    if sys.platform == "win32":
        candidates = [
            Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
    return None


def convert_office_file(
    source_path: Path,
    *,
    out_dir: Path,
    target_ext: str,
) -> Path:
    """Convert ``source_path`` to ``target_ext`` under ``out_dir``; return output path."""

    soffice = resolve_soffice_executable()
    if soffice is None:
        raise AppError(
            "translate.legacy_office_unavailable",
            "处理 .doc 需要安装 LibreOffice（soffice），或先将文件另存为 .docx。",
            422,
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        target_ext,
        "--outdir",
        str(out_dir),
        str(source_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.doc_translate_soffice_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise AppError("translate.legacy_office_timeout", "Office 格式转换超时。", 504) from e
    except OSError as e:
        raise AppError(
            "translate.legacy_office_unavailable",
            "无法启动 LibreOffice 进行 .doc 转换。",
            422,
        ) from e
    if proc.returncode != 0:
        log.warning(
            "soffice convert failed rc=%s stderr=%s",
            proc.returncode,
            (proc.stderr or "")[:500],
        )
        raise AppError("translate.legacy_office_failed", "Office 格式转换失败。", 502)
    out_path = out_dir / f"{source_path.stem}.{target_ext}"
    if not out_path.is_file():
        raise AppError("translate.legacy_office_failed", "未找到转换后的文件。", 502)
    return out_path
