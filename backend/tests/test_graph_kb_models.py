"""GraphKB ORM table names and required columns."""

from app.graph_kb.domain.db.models import GraphKb, GraphKbMember


def test_graph_kb_table_and_columns() -> None:
    assert GraphKb.__tablename__ == "graph_kb"
    cols = {c.key for c in GraphKb.__table__.columns}
    assert {"workspace_id", "engine", "permission", "created_by"} <= cols


def test_member_unique_constraint_name() -> None:
    names = {c.name for c in GraphKbMember.__table__.constraints}
    assert "uq_graph_kb_member_graph_user" in names
