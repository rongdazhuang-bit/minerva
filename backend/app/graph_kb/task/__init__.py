"""Celery tasks for GraphKB index and cleanup (autodiscovered as ``app.graph_kb.task``)."""

from app.graph_kb.task.cleanup_task import graph_kb_cleanup_task
from app.graph_kb.task.index_task import graph_kb_index_task

__all__ = ["graph_kb_cleanup_task", "graph_kb_index_task"]
