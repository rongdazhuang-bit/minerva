"""GraphKB HTTP router registration and prefix."""


def test_router_prefix() -> None:
    """Router must mount under workspace-scoped ``graph-kbs``."""

    from app.graph_kb.api.router import router

    assert router.prefix == "/workspaces/{workspace_id}/graph-kbs"
