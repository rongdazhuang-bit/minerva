"""Build GraphRAG silo paths from workspace_id + graph_id only."""

from pathlib import Path
from uuid import UUID


def graphrag_root(data_root: Path, workspace_id: UUID, graph_id: UUID) -> Path:
    """Return GraphRAG silo directory ``{data_root}/{workspace_id}/{graph_id}``.

    Must stay identical to ``backend.app.graph_kb.domain.namespace.graphrag_root``.
    Never accept a client-supplied ``root`` string.
    """

    return Path(data_root) / str(workspace_id) / str(graph_id)
