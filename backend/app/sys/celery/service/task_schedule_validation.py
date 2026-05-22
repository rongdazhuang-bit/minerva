"""Validate ``sys_celery`` args/kwargs against known Celery task entry signatures."""

from __future__ import annotations

import uuid
from typing import Any

from app.translate.domain.constants import DOC_TRANSLATE_RUN_TASK_NAME


def parse_doc_translate_job_uuid(value: str | None) -> uuid.UUID | None:
    """Return a UUID when ``value`` is a valid ``doc_translate_job.id``, else ``None``."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except ValueError:
        return None


def _raw_doc_translate_job_id(
    args: list[Any] | tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str | None:
    """Extract unparsed job id string from beat/run-now payload."""

    if args:
        candidate = args[0]
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    raw = kwargs.get("job_id")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return None


def resolve_doc_translate_job_id(
    args: list[Any] | tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str | None:
    """Extract a valid UUID ``job_id`` from beat/run-now payload."""

    raw = _raw_doc_translate_job_id(args, kwargs)
    if raw is None:
        return None
    parsed = parse_doc_translate_job_uuid(raw)
    if parsed is None:
        return None
    return str(parsed)


def validate_celery_schedule_payload(
    task_name: str,
    args: list[Any],
    kwargs: dict[str, Any],
) -> None:
    """Raise ``ValueError`` when a periodic job payload cannot invoke ``task_name``."""

    name = task_name.strip()
    if name == DOC_TRANSLATE_RUN_TASK_NAME:
        raw = _raw_doc_translate_job_id(args, kwargs)
        if raw is None:
            raise ValueError(
                "translate.run_job 需要已存在的 doc_translate_job.id："
                "在 args_json 首元素或 kwargs_json.job_id 中填写 UUID。"
                "新建翻译任务请走上传 API（会自动入队），不要用 demo 占位符 [\"minerva\"]。"
            )
        if parse_doc_translate_job_uuid(raw) is None:
            raise ValueError(
                f"translate.run_job 的 job_id 必须是 doc_translate_job 表中的 UUID（当前为 {raw!r}）。"
                "请从「文档翻译」任务列表复制任务 id，勿随机生成或沿用 demo.default_job 的 [\"minerva\"]。"
            )
