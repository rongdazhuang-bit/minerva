"""pgvector-backed vector storage for dataset segments."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

from app.config import settings
from app.dataset.infrastructure.vector.base import BaseVector
from app.dataset.rag.models import RagDocument


def _pg_conn_params() -> dict[str, Any]:
    """Resolve psycopg2 connection kwargs from dataset or main DB URL."""

    raw = (settings.dataset_pgvector_url or settings.sync_database_url or "").strip()
    parsed = urlparse(raw)
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 5432,
        "user": parsed.username or "minerva",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/minerva").lstrip("/"),
    }


def _vector_literal(values: list[float]) -> str:
    """Format embedding list for pgvector SQL literal."""

    return "[" + ",".join(str(float(v)) for v in values) + "]"


class PGVectorStore(BaseVector):
    """Store embeddings in ``embedding_{collection}`` tables with pgvector."""

    def __init__(self, collection_name: str) -> None:
        """Open connections and ensure extension exists."""

        super().__init__(collection_name)
        self._table = f"embedding_{collection_name.replace('-', '_')}"
        self._ensure_extension()

    def get_type(self) -> str:
        """Return backend slug."""

        return "pgvector"

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        """Yield a psycopg2 cursor with auto-commit."""

        conn = psycopg2.connect(**_pg_conn_params())
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def _ensure_extension(self) -> None:
        """Create pgvector extension if missing."""

        with self._cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def _ensure_table(self, dimension: int) -> None:
        """Create embedding table and index for ``dimension``."""

        with self._cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id UUID PRIMARY KEY,
                    text TEXT NOT NULL,
                    meta JSONB NOT NULL,
                    embedding vector({dimension}) NOT NULL
                )
                """
            )
            idx_hash = hashlib.md5(self._table.encode()).hexdigest()[:8]
            try:
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS embedding_cosine_{idx_hash}
                    ON {self._table}
                    USING hnsw (embedding vector_cosine_ops)
                    """
                )
            except Exception:
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS embedding_cosine_{idx_hash}
                    ON {self._table}
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                    """
                )

    def create(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Create table then insert."""

        if not embeddings:
            return []
        self._ensure_table(len(embeddings[0]))
        return self.add_texts(texts, embeddings)

    def add_texts(self, texts: list[RagDocument], embeddings: list[list[float]]) -> list[str]:
        """Bulk insert embedding rows."""

        if not texts:
            return []
        self._ensure_table(len(embeddings[0]))
        values: list[tuple[Any, ...]] = []
        ids: list[str] = []
        for doc, emb in zip(texts, embeddings, strict=True):
            doc_id = (doc.metadata or {}).get("doc_id") or str(uuid.uuid4())
            ids.append(str(doc_id))
            values.append((doc_id, doc.page_content, json.dumps(doc.metadata or {}), _vector_literal(emb)))
        with self._cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                f"INSERT INTO {self._table} (id, text, meta, embedding) VALUES %s",
                values,
                template="(%s, %s, %s::jsonb, %s::vector)",
            )
        return ids

    def delete_by_metadata_field(self, key: str, value: str) -> None:
        """Delete rows where metadata JSON field matches."""

        with self._cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE meta ->> %s = %s",
                (key, value),
            )

    def delete_collection(self) -> None:
        """Drop embedding table for this collection."""

        with self._cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self._table}")

    def search_by_vector(self, query_vector: list[float], *, top_k: int = 3) -> list[RagDocument]:
        """Cosine similarity search."""

        query_literal = _vector_literal(query_vector)
        with self._cursor() as cur:
            cur.execute(
                f"""
                SELECT text, meta, (embedding <=> %s::vector) AS score
                FROM {self._table}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_literal, query_literal, top_k),
            )
            rows = cur.fetchall()
        docs: list[RagDocument] = []
        for text, meta, score in rows:
            metadata = meta if isinstance(meta, dict) else json.loads(meta)
            metadata["score"] = float(score)
            docs.append(RagDocument(page_content=text, metadata=metadata))
        return docs
