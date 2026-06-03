"""Factory for memory retrieve/persist strategy pairs."""

from __future__ import annotations

from app.agent.memory.protocols import MemoryPersistStrategy, MemoryRetrieveStrategy
from app.config import settings


def create_memory_strategies() -> tuple[MemoryRetrieveStrategy, MemoryPersistStrategy]:
    """Return a matched retrieve/persist pair for ``settings.agent_memory_backend``."""

    if settings.agent_memory_backend == "mem0":
        from app.agent.memory.mem0.persist import Mem0MemoryPersistStrategy
        from app.agent.memory.mem0.retrieve import Mem0MemoryRetrieveStrategy

        return Mem0MemoryRetrieveStrategy(), Mem0MemoryPersistStrategy()

    from app.agent.memory.sql.persist import SqlMemoryPersistStrategy
    from app.agent.memory.sql.retrieve import SqlMemoryRetrieveStrategy

    return SqlMemoryRetrieveStrategy(), SqlMemoryPersistStrategy()
