from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ecommerce_storage.port import ObjectStorageError, validate_key
from ecommerce_storage.urls import build_public_url

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

DEFAULT_REGION = "us-east-1"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_READ_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class S3Settings:
    access_key: str
    secret_key: str
    region: str = DEFAULT_REGION
    endpoint_url: str | None = None
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            access_key=environ["OBJECT_STORAGE_ACCESS_KEY"],
            secret_key=environ["OBJECT_STORAGE_SECRET_KEY"],
            region=environ.get("OBJECT_STORAGE_REGION", DEFAULT_REGION),
            endpoint_url=environ.get("OBJECT_STORAGE_ENDPOINT") or None,
        )


def build_s3_client(settings: S3Settings) -> S3Client:
    return boto3.client(
        "s3",
        region_name=settings.region,
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        config=Config(
            s3={"addressing_style": "path"}
            if settings.endpoint_url
            else {"addressing_style": "auto"},
            connect_timeout=settings.connect_timeout_seconds,
            read_timeout=settings.read_timeout_seconds,
            retries={"total_max_attempts": settings.max_attempts, "mode": "standard"},
        ),
    )


class S3ObjectStorage:
    def __init__(self, client: S3Client, bucket: str, public_base_url: str) -> None:
        self._client = client
        self._bucket = bucket
        self._public_base_url = public_base_url

    async def put(
        self, key: str, data: bytes, content_type: str, cache_control: str | None = None
    ) -> None:
        key = validate_key(key)

        def upload() -> None:
            if cache_control is None:
                self._client.put_object(
                    Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
                )
            else:
                self._client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                    CacheControl=cache_control,
                )

        await self._call(upload)

    async def delete(self, key: str) -> None:
        validated = validate_key(key)

        def remove() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=validated)

        await self._call(remove)

    async def _call(self, operation: Callable[[], None]) -> None:
        try:
            await asyncio.to_thread(operation)
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageError(f"object storage request failed: {error}") from error

    def public_url(self, key: str) -> str:
        return build_public_url(self._public_base_url, key)
