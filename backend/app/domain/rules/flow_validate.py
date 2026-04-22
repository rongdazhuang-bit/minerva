from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

FlowSchemaVersion = Literal[1]


class RFNode(BaseModel):
    id: str
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class RFEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class ReactFlowDocument(BaseModel):
    schema_version: FlowSchemaVersion = 1
    nodes: list[RFNode] = Field(default_factory=list)
    edges: list[RFEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _whitelist(self) -> ReactFlowDocument:
        allowed = {
            "start",
            "end",
            "branch",
            "http_request",
            "poll",
            "queue_publish",
            "noop",
        }
        for n in self.nodes:
            if n.type not in allowed:
                msg = f"unknown node type: {n.type}"
                raise ValueError(msg)
        has_end = any(n.type == "end" for n in self.nodes)
        if not has_end:
            raise ValueError("flow.missing_end")
        return self


def parse_flow(flow: dict[str, Any]) -> ReactFlowDocument:
    return ReactFlowDocument.model_validate(flow)
