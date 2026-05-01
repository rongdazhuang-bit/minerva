"""Minimal exports for ``ChatService`` wiring."""

from app.llm.service.chat_service import ChatService, chat_service

__all__ = ["ChatService", "chat_service"]
