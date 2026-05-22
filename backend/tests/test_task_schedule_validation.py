"""Tests for sys_celery task payload validation."""

from __future__ import annotations

import pytest

from app.sys.celery.service import task_schedule_validation as validation
from app.translate.domain.constants import DOC_TRANSLATE_RUN_TASK_NAME


_JOB_UUID = "550e8400-e29b-41d4-a716-446655440000"


def test_resolve_doc_translate_job_id_from_positional() -> None:
    """First args_json element is treated as job_id when it is a UUID."""

    assert validation.resolve_doc_translate_job_id([_JOB_UUID], {"source": "scheduler"}) == _JOB_UUID


def test_resolve_doc_translate_job_id_from_kwargs() -> None:
    """kwargs_json.job_id is accepted when args are empty."""

    assert validation.resolve_doc_translate_job_id([], {"job_id": _JOB_UUID}) == _JOB_UUID


def test_validate_translate_run_job_rejects_demo_kwargs() -> None:
    """Periodic translate.run_job without job_id is rejected at schedule build time."""

    with pytest.raises(ValueError, match="job_id"):
        validation.validate_celery_schedule_payload(
            DOC_TRANSLATE_RUN_TASK_NAME,
            [],
            {"source": "scheduler"},
        )


def test_validate_translate_run_job_rejects_demo_minerva_arg() -> None:
    """Demo args_json [\"minerva\"] is not a valid doc_translate_job UUID."""

    with pytest.raises(ValueError, match="UUID"):
        validation.validate_celery_schedule_payload(
            DOC_TRANSLATE_RUN_TASK_NAME,
            ["minerva"],
            {"source": "scheduler"},
        )


def test_resolve_doc_translate_job_id_rejects_non_uuid() -> None:
    """Non-UUID strings are treated as missing job_id."""

    assert validation.resolve_doc_translate_job_id(["minerva"], {}) is None


def test_validate_translate_run_job_accepts_job_id() -> None:
    """translate.run_job with job_id passes validation."""

    validation.validate_celery_schedule_payload(
        DOC_TRANSLATE_RUN_TASK_NAME,
        ["550e8400-e29b-41d4-a716-446655440000"],
        {"source": "scheduler"},
    )
