"""LightRAG store: uncached delete_namespace and reindex rebuild."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.store import LightRAGStore


class _Droppable:
    """Storage stub whose ``drop`` is recorded."""

    def __init__(self) -> None:
        self.drop = AsyncMock()


def _dummy_rag() -> SimpleNamespace:
    """Minimal LightRAG-shaped object with droppable storages and ainsert."""

    return SimpleNamespace(
        full_docs=_Droppable(),
        text_chunks=_Droppable(),
        llm_response_cache=_Droppable(),
        entities_vdb=_Droppable(),
        relationships_vdb=_Droppable(),
        chunks_vdb=_Droppable(),
        chunk_entity_relation_graph=_Droppable(),
        doc_status=_Droppable(),
        ainsert=AsyncMock(),
        finalize_storages=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_delete_namespace_opens_uncached_workspace() -> None:
    """Cache miss must still open the workspace and wipe storages."""

    store = LightRAGStore()
    rag = _dummy_rag()
    store._get_rag = AsyncMock(return_value=rag)  # type: ignore[method-assign]

    await store.delete_namespace(workspace_id=uuid4(), graph_id=uuid4())

    store._get_rag.assert_awaited()
    rag.full_docs.drop.assert_awaited()
    rag.doc_status.drop.assert_awaited()
    rag.finalize_storages.assert_awaited()
    assert store._cache == {}


@pytest.mark.asyncio
async def test_index_wipes_before_insert_so_deleted_docs_drop() -> None:
    """Reindex rebuilds the workspace from the current request document list."""

    store = LightRAGStore()
    rag = _dummy_rag()
    store._get_rag = AsyncMock(return_value=rag)  # type: ignore[method-assign]
    store.export_graph = AsyncMock(return_value={"entities": [], "relations": []})  # type: ignore[method-assign]

    await store.index(
        workspace_id=uuid4(),
        graph_id=uuid4(),
        documents=[{"document_id": str(uuid4()), "name": "kept.txt", "text": "keep-me"}],
    )

    rag.full_docs.drop.assert_awaited()
    rag.ainsert.assert_awaited()
    assert "keep-me" in rag.ainsert.await_args.args
