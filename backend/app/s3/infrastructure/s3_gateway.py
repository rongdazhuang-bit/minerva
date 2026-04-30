"""S3 gateway abstraction and boto3-backed implementation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from app.exceptions import AppError
from app.s3.domain.models import S3DownloadProxy, S3ObjectItem, S3StorageConfig
from app.s3.infrastructure.client_factory import create_s3_client


class S3Gateway(Protocol):
    """Protocol for S3 operations used by application services."""

    def upload_object(
        self,
        *,
        bucket: str,
        object_key: str,
        payload: bytes,
        content_type: str | None,
    ) -> None:
        """Upload one object body to S3."""

    def list_objects(self, *, bucket: str, prefix: str) -> list[S3ObjectItem]:
        """Return all objects under the provided prefix."""

    def create_presigned_download_url(
        self, *, bucket: str, object_key: str, expires_in: int
    ) -> str:
        """Create one presigned URL for object download."""

    def open_download_stream(self, *, bucket: str, object_key: str) -> S3DownloadProxy:
        """Open a download stream for proxy mode."""

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        """Delete one object by key."""


class Boto3S3Gateway:
    """Boto3-based gateway implementation for workspace S3 storage."""

    def __init__(self, client: Any) -> None:
        """Store a prepared boto3 S3 client."""

        self._client = client

    def upload_object(
        self,
        *,
        bucket: str,
        object_key: str,
        payload: bytes,
        content_type: str | None,
    ) -> None:
        """Upload object bytes to a target bucket/key."""

        params: dict[str, Any] = {"Bucket": bucket, "Key": object_key, "Body": payload}
        if content_type:
            params["ContentType"] = content_type
        self._run(self._client.put_object, **params)

    def list_objects(self, *, bucket: str, prefix: str) -> list[S3ObjectItem]:
        """Return all object rows for one bucket prefix."""

        paginator = self._client.get_paginator("list_objects_v2")
        pages: Iterable[dict[str, Any]] = self._run(
            paginator.paginate,
            Bucket=bucket,
            Prefix=prefix,
        )
        items: list[S3ObjectItem] = []
        for page in pages:
            for raw in page.get("Contents") or []:
                items.append(
                    S3ObjectItem(
                        object_key=str(raw.get("Key") or ""),
                        size=int(raw.get("Size") or 0),
                        last_modified=raw.get("LastModified"),
                    )
                )
        items.sort(key=lambda item: item.object_key)
        return items

    def create_presigned_download_url(
        self, *, bucket: str, object_key: str, expires_in: int
    ) -> str:
        """Build a short-lived object download URL."""

        return str(
            self._run(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )
        )

    def open_download_stream(self, *, bucket: str, object_key: str) -> S3DownloadProxy:
        """Open and return object stream metadata for proxy download mode."""

        response: dict[str, Any] = self._run(
            self._client.get_object,
            Bucket=bucket,
            Key=object_key,
        )
        body = response["Body"]
        return S3DownloadProxy(
            stream=body,
            content_type=response.get("ContentType"),
            content_length=response.get("ContentLength"),
        )

    def delete_object(self, *, bucket: str, object_key: str) -> None:
        """Delete object and ensure key exists before deleting."""

        self._run(self._client.head_object, Bucket=bucket, Key=object_key)
        self._run(self._client.delete_object, Bucket=bucket, Key=object_key)

    def _run(self, fn, *args: Any, **kwargs: Any) -> Any:
        """Execute boto3 call and map provider errors to ``AppError``."""

        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - unified provider error mapping.
            _raise_s3_error(exc)


def create_s3_gateway(config: S3StorageConfig) -> S3Gateway:
    """Create one S3 gateway from a validated storage config."""

    client = create_s3_client(config)
    return Boto3S3Gateway(client)


def _raise_s3_error(exc: Exception) -> None:
    """Translate boto errors into stable S3 ``AppError`` codes."""

    try:
        from botocore.exceptions import ClientError, EndpointConnectionError
    except ImportError:
        raise AppError("s3.request_failed", str(exc) or "S3 request failed", 502) from exc

    if isinstance(exc, EndpointConnectionError):
        raise AppError("s3.endpoint_unreachable", "S3 endpoint is unreachable", 502) from exc
    if isinstance(exc, ClientError):
        error_code = str((exc.response or {}).get("Error", {}).get("Code") or "")
        if error_code in {"NoSuchKey", "NotFound", "404"}:
            raise AppError("s3.object_not_found", "S3 object not found", 404) from exc
        if error_code == "NoSuchBucket":
            raise AppError("s3.bucket_not_found", "S3 bucket not found", 404) from exc
        if error_code in {
            "AccessDenied",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
            "AuthorizationHeaderMalformed",
        }:
            raise AppError("s3.access_denied", "S3 access denied", 403) from exc
        raise AppError("s3.request_failed", f"S3 request failed: {error_code}", 502) from exc
    raise AppError("s3.request_failed", str(exc) or "S3 request failed", 502) from exc
