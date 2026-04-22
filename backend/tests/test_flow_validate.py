import pytest

from app.domain.rules.flow_validate import parse_flow


def test_flow_rejects_missing_end() -> None:
    flow = {
        "schema_version": 1,
        "nodes": [{"id": "1", "type": "start", "data": {}}],
        "edges": [],
    }
    with pytest.raises(ValueError, match="flow.missing_end"):
        parse_flow(flow)


def test_flow_rejects_unknown_node() -> None:
    bad = {
        "schema_version": 1,
        "nodes": [{"id": "1", "type": "not_real", "data": {}}],
        "edges": [],
    }
    with pytest.raises(ValueError, match="unknown node type"):
        parse_flow(bad)
