"""Namespace formula must match Minerva backend ``lightrag_workspace``."""

from uuid import UUID

from app.namespace import lightrag_workspace


def test_lightrag_workspace_uses_hex_ids() -> None:
    """Same UUIDs as Task 1 must yield the same kg_{hex}_{hex} string."""

    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    assert lightrag_workspace(wid, gid) == (
        "kg_11111111111111111111111111111111_22222222222222222222222222222222"
    )
