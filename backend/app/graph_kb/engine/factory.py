"""Factory selecting Fake vs HTTP GraphEngineClient from Settings."""

from __future__ import annotations

from app.config import settings
from app.graph_kb.engine.fake_client import FakeGraphEngineClient
from app.graph_kb.engine.http_client import HttpGraphEngineClient
from app.graph_kb.engine.protocol import GraphEngineClient


def create_engine_client() -> GraphEngineClient:
    """Return Fake when ``GRAPH_KB_ENGINE_CLIENT=fake``, otherwise HTTP adapter."""

    if settings.graph_kb_engine_client == "fake":
        return FakeGraphEngineClient()
    return HttpGraphEngineClient()
