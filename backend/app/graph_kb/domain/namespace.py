"""Build engine namespaces from workspace_id + graph_id only."""

from pathlib import Path
from uuid import UUID


def lightrag_workspace(workspace_id: UUID, graph_id: UUID) -> str:
    """Return LightRAG workspace key ``kg_{wid_hex}_{gid_hex}``."""

    return f"kg_{workspace_id.hex}_{graph_id.hex}"


def graphrag_root(data_root: Path, workspace_id: UUID, graph_id: UUID) -> Path:
    """Return GraphRAG silo directory ``{data_root}/{workspace_id}/{graph_id}``."""

    return Path(data_root) / str(workspace_id) / str(graph_id)
