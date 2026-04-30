"""Factory functions that build boto3 S3 clients from validated config."""

from __future__ import annotations

from typing import Any

from app.s3.domain.models import S3StorageConfig


def create_s3_client(config: S3StorageConfig) -> Any:
    """Create and return one boto3 S3 client for a workspace config."""

    import boto3

    kwargs: dict[str, Any] = {}
    if config.endpoint_url:
        kwargs["endpoint_url"] = config.endpoint_url
    if config.auth_type == "API_KEY":
        kwargs["aws_access_key_id"] = config.api_key
        kwargs["aws_secret_access_key"] = "-"
    elif config.auth_type == "BASIC":
        kwargs["aws_access_key_id"] = config.auth_name
        kwargs["aws_secret_access_key"] = config.auth_passwd
    return boto3.client("s3", **kwargs)
