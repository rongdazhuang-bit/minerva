"""Build LangChain chat models from workspace SysModel rows."""

from __future__ import annotations

import uuid

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.direct_endpoint_openai_client import (
    build_direct_endpoint_async_openai,
)
from app.agent.infrastructure.thinking_config import ThinkingConfig
from app.exceptions import AppError
from app.llm.strategies.openai_compatible import normalize_openai_base_url
from app.sys.model_provider.domain.db.models import SysModel
from app.sys.model_provider.infrastructure import repository as model_repo


class ChatModelFactory:
    """Resolve ``SysModel`` into a LangChain chat model for agent graphs."""

    @staticmethod
    def from_sys_model_row(
        row: SysModel,
        *,
        workspace_id: uuid.UUID,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: ThinkingConfig | None = None,
    ) -> BaseChatModel:
        """Validate workspace ownership and enabled flag, then construct the client."""

        if row.workspace_id != workspace_id:
            raise AppError("agent.model_not_found", "模型不存在或不属于当前工作区。")
        if not row.enabled:
            raise AppError("agent.model_disabled", "模型未启用。")
        endpoint_url = normalize_openai_base_url((row.endpoint_url or "").strip())
        if not endpoint_url:
            raise AppError("agent.model_misconfigured", "模型缺少 endpoint_url。")
        api_key = (row.api_key or "").strip()
        if not api_key:
            raise AppError("agent.model_misconfigured", "模型缺少 api_key。")
        root_async_client = build_direct_endpoint_async_openai(
            endpoint_url=endpoint_url,
            api_key=api_key,
        )
        # LangChain recreates root_async_client when async_client is omitted; bind both.
        kwargs: dict = {
            "model": row.model_name,
            "api_key": api_key,
            "root_async_client": root_async_client,
            "async_client": root_async_client.chat.completions,
            "stream_usage": True,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        effective_max = max_tokens
        if effective_max is None and row.max_tokens_to_sample is not None:
            effective_max = row.max_tokens_to_sample
        if effective_max is not None:
            kwargs["max_tokens"] = effective_max
        if thinking and thinking.enabled and thinking.extra_body:
            kwargs["model_kwargs"] = {"extra_body": dict(thinking.extra_body)}
        return ChatOpenAI(**kwargs)

    @staticmethod
    async def get(
        session: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        model_id: uuid.UUID,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> BaseChatModel:
        """Load ``SysModel`` from DB and return a chat model."""

        row = await model_repo.get_for_workspace(
            session, workspace_id=workspace_id, model_id=model_id
        )
        if row is None:
            raise AppError("agent.model_not_found", "模型不存在或不属于当前工作区。")
        return ChatModelFactory.from_sys_model_row(
            row,
            workspace_id=workspace_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )
