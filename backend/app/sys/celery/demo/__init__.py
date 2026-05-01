"""Demo tasks module for Celery scheduler.

This module contains example tasks that can be scheduled via the Celery beat scheduler.
"""

from .default_job import default_job

__all__ = ["default_job"]
