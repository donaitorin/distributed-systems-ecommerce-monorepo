from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import boto3
from botocore.config import Config

from ecommerce_storage.port import validate_key
from ecommerce_storage.urls import build_public_url

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

DEFAULT_REGION = "us-east-1"


@dataclass(frozen=True, slots=True)
class S3Settings:
    access_key: str
    secret_key: str
    region: str = DEFAULT_REGION
    endpoint_url: str | None = None

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
            else {"addressing_style": "auto"}
        ),
    )


class S3ObjectStorage:
    def __init__(self, client: S3Client, bucket: str, public_base_url: str) -> None:
        self._client = client
        self._bucket = bucket
        self._public_base_url = public_base_url

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=validate_key(key),
            Body=data,
            ContentType=content_type,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=validate_key(key)
        )

    def public_url(self, key: str) -> str:
        return build_public_url(self._public_base_url, key)
