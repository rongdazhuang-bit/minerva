"""Build LightRAG workspace keys from workspace_id + graph_id only."""

from uuid import UUID


def lightrag_workspace(workspace_id: UUID, graph_id: UUID) -> str:
    """Return LightRAG workspace key ``kg_{wid_hex}_{gid_hex}``.

    Must stay identical to ``backend.app.graph_kb.domain.namespace.lightrag_workspace``.
    """

    return f"kg_{workspace_id.hex}_{graph_id.hex}"
