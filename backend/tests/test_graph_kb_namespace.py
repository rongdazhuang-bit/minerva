"""Namespace helpers for GraphKB engine isolation."""

from pathlib import Path
from uuid import UUID

from app.core.security.permission_codes import FEATURE_GRAPH_KB, menu_key_to_feature
from app.graph_kb.domain.namespace import graphrag_root, lightrag_workspace


def test_lightrag_workspace_uses_hex_ids() -> None:
    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    assert lightrag_workspace(wid, gid) == (
        "kg_11111111111111111111111111111111_22222222222222222222222222222222"
    )


def test_graphrag_root_nests_workspace_then_graph(tmp_path: Path) -> None:
    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    root = graphrag_root(tmp_path, wid, gid)
    assert root == tmp_path / str(wid) / str(gid)


def test_menu_maps_to_feature() -> None:
    assert menu_key_to_feature("sub-graph-kb") == FEATURE_GRAPH_KB
    assert menu_key_to_feature("graph-kb-list") == FEATURE_GRAPH_KB
