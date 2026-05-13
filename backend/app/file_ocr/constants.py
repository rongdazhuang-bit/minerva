"""Shared literals for the file OCR vertical module."""

from __future__ import annotations

# Celery task name; must match ``sys_celery.task`` when scheduling from the database.
FILE_OCR_SCAN_INIT_TASK_NAME = "file_ocr.scan_init"

# Max rows claimed per scheduler tick to bound HTTP and DB work inside one beat cycle.
FILE_OCR_SCAN_BATCH_SIZE = 25

# OCR types picked up by the INIT scanner in the current release (MinerU is registered but excluded here).
FILE_OCR_SUPPORTED_SCAN_OCR_TYPES: frozenset[str] = frozenset({"PADDLE_OCR"})

# Bound persisted failure text on ``ocr_file.remark`` for worker safety.
FILE_OCR_REMARK_MAX_LEN = 4000
