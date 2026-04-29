"""Pydantic payloads for provider/model catalog APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelProviderCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider_name: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=128)
    model_type: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    load_balancing_enabled: bool = False
    auth_type: str = Field(min_length=1, max_length=64)
    endpoint_url: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=128)
    auth_name: str | None = Field(default=None, max_length=64)
    auth_passwd: str | None = Field(default=None, max_length=128)
    context_size: int | None = Field(default=None, ge=1, le=32767)
    max_tokens_to_sample: int | None = Field(default=None, ge=1, le=32767)
    other_config: str | None = Field(default=None, alias="model_config")


class ModelProviderPatchIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider_name: str | None = Field(default=None, min_length=1, max_length=128)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    model_type: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None
    load_balancing_enabled: bool | None = None
    auth_type: str | None = Field(default=None, min_length=1, max_length=64)
    endpoint_url: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=128)
    auth_name: str | None = Field(default=None, max_length=64)
    auth_passwd: str | None = Field(default=None, max_length=128)
    context_size: int | None = Field(default=None, ge=1, le=32767)
    max_tokens_to_sample: int | None = Field(default=None, ge=1, le=32767)
    other_config: str | None = Field(default=None, alias="model_config")


class ModelProviderListItemOut(BaseModel):
    # Alias model_config: allow constructor kwargs as other_config= (see router mappers)
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    provider_name: str
    model_name: str
    model_type: str
    enabled: bool
    load_balancing_enabled: bool
    auth_type: str
    endpoint_url: str | None
    has_api_key: bool
    has_password: bool
    context_size: int | None
    max_tokens_to_sample: int | None
    other_config: str | None = Field(
        default=None,
        alias="model_config",
        serialization_alias="model_config",
    )
    create_at: datetime | None
    update_at: datetime | None


class ModelProviderDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    provider_name: str
    model_name: str
    model_type: str
    enabled: bool
    load_balancing_enabled: bool
    auth_type: str
    endpoint_url: str | None
    api_key: str | None
    auth_name: str | None
    auth_passwd: str | None
    context_size: int | None
    max_tokens_to_sample: int | None
    other_config: str | None = Field(
        default=None,
        alias="model_config",
        serialization_alias="model_config",
    )
    create_at: datetime | None
    update_at: datetime | None


class ModelProviderGroupItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    model_name: str
    model_type: str
    enabled: bool
    load_balancing_enabled: bool
    auth_type: str
    endpoint_url: str | None
    has_api_key: bool
    has_password: bool
    context_size: int | None
    max_tokens_to_sample: int | None
    other_config: str | None = Field(
        default=None,
        alias="model_config",
        serialization_alias="model_config",
    )
    create_at: datetime | None
    update_at: datetime | None


class ModelProviderGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider_name: str
    items: list[ModelProviderGroupItemOut]
