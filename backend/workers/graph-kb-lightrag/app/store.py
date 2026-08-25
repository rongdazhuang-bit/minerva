"""In-memory and LightRAG-backed stores for the graph-kb worker."""

from __future__ import annotations

import os
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.config import settings
from app.namespace import lightrag_workspace

# Max cached LightRAG instances per worker process (LRU eviction).
_MAX_LIGHTRAG_INSTANCES = 16


def worker_fake_enabled() -> bool:
    """Return True when fake-engine mode is enabled in worker settings."""

    return settings.graph_kb_worker_fake


@dataclass
class _FakeNs:
    """Per-namespace fake index state (mirrors Minerva FakeGraphEngineClient)."""

    texts: list[str] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    summaries: list[dict] = field(default_factory=list)


class FakeStore:
    """Process-local fake engine keyed by ``(workspace_id, graph_id)``."""

    def __init__(self) -> None:
        """Initialize an empty in-memory namespace map."""

        self._store: dict[tuple[UUID, UUID], _FakeNs] = {}

    def _ns(self, workspace_id: UUID, graph_id: UUID) -> _FakeNs:
        """Return (creating if needed) the store for one workspace+graph pair."""

        key = (workspace_id, graph_id)
        if key not in self._store:
            self._store[key] = _FakeNs()
        return self._store[key]

    async def index(
        self,
        *,
        workspace_id: UUID,
        graph_id: UUID,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Index docs into one entity + relation + summary (fake projection)."""

        ns = self._ns(workspace_id, graph_id)
        texts = [str(d.get("text") or "") for d in documents]
        joined = "\n".join(texts)
        entity_id = f"ent-{graph_id.hex[:8]}"
        entity = {
            "id": entity_id,
            "name": joined
            or (str(documents[0].get("name") or "empty") if documents else "empty"),
            "type": "document",
            "description": joined,
        }
        relation = {
            "id": f"rel-{graph_id.hex[:8]}",
            "from_id": entity_id,
            "to_id": entity_id,
            "type": "self",
            "description": "fake index relation",
        }
        summary = {
            "summary_id": f"sum-{graph_id.hex[:8]}",
            "title": f"Summary {graph_id.hex[:8]}",
            "content": joined,
            "level": 0,
            "parent_id": None,
        }
        ns.texts = texts
        ns.entities = [entity]
        ns.relations = [relation]
        ns.summaries = [summary]
        return {"entities": list(ns.entities), "relations": list(ns.relations)}

    async def query(
        self,
        *,
        workspace_id: UUID,
        graph_id: UUID,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Return ``fake:`` plus indexed document text for the target graph."""

        _ = mode, top_k
        ns = self._ns(workspace_id, graph_id)
        joined = "\n".join(ns.texts) if ns.texts else query
        return {"answer": f"fake:{joined}", "citations": []}

    async def export_graph(
        self, *, workspace_id: UUID, graph_id: UUID
    ) -> dict[str, Any]:
        """Return entities/relations stored for this namespace."""

        ns = self._ns(workspace_id, graph_id)
        return {"entities": list(ns.entities), "relations": list(ns.relations)}

    async def list_summaries(
        self, *, workspace_id: UUID, graph_id: UUID
    ) -> list[dict[str, Any]]:
        """Return fake summaries for this namespace."""

        return list(self._ns(workspace_id, graph_id).summaries)

    async def delete_namespace(
        self, *, workspace_id: UUID, graph_id: UUID
    ) -> None:
        """Drop the in-memory store for this workspace+graph pair."""

        self._store.pop((workspace_id, graph_id), None)


def _apply_postgres_env_from_database_url() -> None:
    """Map worker database URL into LightRAG ``POSTGRES_*`` vars."""

    raw = (settings.graph_kb_lightrag_database_url or "").strip()
    if not raw:
        return
    parsed = urlparse(raw)
    if parsed.hostname:
        os.environ.setdefault("POSTGRES_HOST", parsed.hostname)
    if parsed.port:
        os.environ.setdefault("POSTGRES_PORT", str(parsed.port))
    if parsed.username:
        os.environ.setdefault("POSTGRES_USER", parsed.username)
    if parsed.password:
        os.environ.setdefault("POSTGRES_PASSWORD", parsed.password)
    if parsed.path and parsed.path != "/":
        os.environ.setdefault("POSTGRES_DATABASE", parsed.path.lstrip("/"))


class LightRAGStore:
    """Real LightRAG engine with PG storages and process-local LRU cache."""

    def __init__(self) -> None:
        """Create an empty LRU map for LightRAG instances."""

        # workspace string -> LightRAG instance
        self._cache: OrderedDict[str, Any] = OrderedDict()

    def _evict_if_needed(self) -> None:
        """Evict least-recently-used instances beyond ``_MAX_LIGHTRAG_INSTANCES``."""

        while len(self._cache) > _MAX_LIGHTRAG_INSTANCES:
            self._cache.popitem(last=False)

    async def _get_rag(
        self,
        *,
        workspace_id: UUID,
        graph_id: UUID,
    ) -> Any:
        """Return a cached or newly constructed LightRAG for the namespace."""

        # Lazy import: never pull SDK into the process when fake mode is on.
        from lightrag import LightRAG
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import EmbeddingFunc

        ws = lightrag_workspace(workspace_id, graph_id)
        if ws in self._cache:
            self._cache.move_to_end(ws)
            return self._cache[ws]

        _apply_postgres_env_from_database_url()

        llm = settings.llm_credentials()
        embedding = settings.embedding_credentials()
        llm_base = llm.get("base_url") or None
        llm_key = llm.get("api_key") or ""
        llm_model = llm.get("model") or "gpt-4o-mini"
        emb_base = embedding.get("base_url") or None
        emb_key = embedding.get("api_key") or ""
        emb_model = embedding.get("model") or "text-embedding-3-small"

        async def llm_model_func(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list | None = None,
            **kwargs: Any,
        ) -> str:
            """Complete via OpenAI-compatible endpoint from worker settings."""

            return await openai_complete_if_cache(
                llm_model,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                api_key=llm_key,
                base_url=llm_base,
                **kwargs,
            )

        async def embedding_func(texts: list[str]) -> Any:
            """Embed texts via OpenAI-compatible endpoint from worker settings."""

            return await openai_embed(
                texts,
                model=emb_model,
                api_key=emb_key,
                base_url=emb_base,
            )

        working_dir = tempfile.mkdtemp(prefix=f"lightrag_{ws}_")
        rag = LightRAG(
            working_dir=working_dir,
            workspace=ws,
            llm_model_func=llm_model_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=settings.graph_kb_embedding_dim,
                max_token_size=8192,
                func=embedding_func,
            ),
            kv_storage="PGKVStorage",
            vector_storage="PGVectorStorage",
            graph_storage="PGGraphStorage",
            doc_status_storage="PGDocStatusStorage",
        )
        await rag.initialize_storages()
        self._cache[ws] = rag
        self._evict_if_needed()
        return rag

    async def index(
        self,
        *,
        workspace_id: UUID,
        graph_id: UUID,
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Insert documents into LightRAG and return an entity/relation export."""

        rag = await self._get_rag(workspace_id=workspace_id, graph_id=graph_id)
        # Rebuild from the current request list so deleted docs do not linger.
        await self._wipe_storages(rag)
        for doc in documents:
            text = str(doc.get("text") or "")
            doc_id = str(doc.get("document_id") or "")
            if not text:
                continue
            # ids keeps Minerva document_id correlation when supported by SDK.
            await rag.ainsert(text, ids=[doc_id] if doc_id else None)
        return await self.export_graph(workspace_id=workspace_id, graph_id=graph_id)

    async def query(
        self,
        *,
        workspace_id: UUID,
        graph_id: UUID,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Run a LightRAG query and normalize answer/citations for Minerva."""

        from lightrag import QueryParam

        rag = await self._get_rag(workspace_id=workspace_id, graph_id=graph_id)
        result = await rag.aquery(
            query, param=QueryParam(mode=mode, top_k=top_k)
        )
        if isinstance(result, dict):
            answer = str(result.get("response") or result.get("answer") or result)
            citations = list(result.get("citations") or [])
        else:
            answer = str(result or "")
            citations = []
        return {"answer": answer, "citations": citations}

    async def export_graph(
        self, *, workspace_id: UUID, graph_id: UUID
    ) -> dict[str, Any]:
        """Export entities and relations from the LightRAG graph storage."""

        ws = lightrag_workspace(workspace_id, graph_id)
        rag = self._cache.get(ws)
        if rag is None:
            rag = await self._get_rag(workspace_id=workspace_id, graph_id=graph_id)
        entities: list[dict] = []
        relations: list[dict] = []
        graph = getattr(rag, "chunk_entity_relation_graph", None)
        if graph is not None and hasattr(graph, "get_all_nodes"):
            nodes = await graph.get_all_nodes()
            for node in nodes or []:
                if isinstance(node, dict):
                    entities.append(node)
                else:
                    entities.append({"id": str(node), "name": str(node)})
        if graph is not None and hasattr(graph, "get_all_edges"):
            edges = await graph.get_all_edges()
            for edge in edges or []:
                if isinstance(edge, dict):
                    relations.append(edge)
                elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
                    relations.append(
                        {
                            "from_id": str(edge[0]),
                            "to_id": str(edge[1]),
                            "type": str(edge[2]) if len(edge) > 2 else "related",
                        }
                    )
        return {"entities": entities, "relations": relations}

    async def list_summaries(
        self, *, workspace_id: UUID, graph_id: UUID
    ) -> list[dict[str, Any]]:
        """List topic / high-level entity summaries from LightRAG KV storage."""

        ws = lightrag_workspace(workspace_id, graph_id)
        rag = self._cache.get(ws)
        if rag is None:
            rag = await self._get_rag(workspace_id=workspace_id, graph_id=graph_id)
        summaries: list[dict[str, Any]] = []
        # Best-effort: entities_vdb or llm_response_cache may hold summary-like rows.
        entities_vdb = getattr(rag, "entities_vdb", None)
        if entities_vdb is not None and hasattr(entities_vdb, "client"):
            try:
                raw = await entities_vdb.client.get()  # type: ignore[misc]
                if isinstance(raw, dict):
                    for key, val in list(raw.items())[:50]:
                        content = ""
                        if isinstance(val, dict):
                            content = str(val.get("content") or val.get("description") or "")
                        summaries.append(
                            {
                                "summary_id": str(key),
                                "title": str(key),
                                "content": content,
                                "level": 0,
                                "parent_id": None,
                            }
                        )
            except Exception:
                pass
        return summaries

    async def _wipe_storages(self, rag: Any) -> None:
        """Best-effort drop LightRAG storage backends for one workspace instance."""

        for attr in (
            "full_docs",
            "text_chunks",
            "llm_response_cache",
            "entities_vdb",
            "relationships_vdb",
            "chunks_vdb",
            "chunk_entity_relation_graph",
            "doc_status",
        ):
            storage = getattr(rag, attr, None)
            if storage is not None and hasattr(storage, "drop"):
                try:
                    await storage.drop()
                except Exception:
                    pass

    async def delete_namespace(
        self, *, workspace_id: UUID, graph_id: UUID
    ) -> None:
        """Open the workspace if uncached, then wipe PG rows and drop the cache.

        Must not return early on a cache miss — leftover engine data would remain.
        """

        ws = lightrag_workspace(workspace_id, graph_id)
        rag = self._cache.pop(ws, None)
        if rag is None:
            rag = await self._get_rag(workspace_id=workspace_id, graph_id=graph_id)
            self._cache.pop(ws, None)
        await self._wipe_storages(rag)
        finalize = getattr(rag, "finalize_storages", None)
        if finalize is not None:
            try:
                await finalize()
            except Exception:
                pass


def build_store() -> FakeStore | LightRAGStore:
    """Return FakeStore when ``GRAPH_KB_WORKER_FAKE=1``, else LightRAGStore."""

    if worker_fake_enabled():
        return FakeStore()
    return LightRAGStore()
