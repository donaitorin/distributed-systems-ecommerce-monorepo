from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ecommerce_storage.port import ObjectNotFoundError, ObjectStorageError, validate_key
from ecommerce_storage.urls import build_public_url

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

DEFAULT_REGION = "us-east-1"
DEFAULT_PART_SIZE = 8 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
MISSING_OBJECT_CODES = frozenset({"NoSuchKey", "404", "NotFound"})
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
    def __init__(
        self,
        client: S3Client,
        bucket: str,
        public_base_url: str,
        part_size: int = DEFAULT_PART_SIZE,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._public_base_url = public_base_url
        self._part_size = part_size

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

    async def put_stream(self, key: str, chunks: AsyncIterator[bytes], content_type: str) -> None:
        validated = validate_key(key)
        buffer = bytearray()
        upload_id: str | None = None
        parts: list[dict[str, str | int]] = []
        try:
            async for chunk in chunks:
                buffer += chunk
                while len(buffer) >= self._part_size:
                    if upload_id is None:
                        upload_id = await self._call(
                            lambda: self._client.create_multipart_upload(
                                Bucket=self._bucket, Key=validated, ContentType=content_type
                            )["UploadId"]
                        )
                    parts.append(
                        await self._upload_part(validated, upload_id, len(parts) + 1, buffer)
                    )
                    del buffer[: self._part_size]
            if upload_id is None:
                data = bytes(buffer)
                await self._call(
                    lambda: self._client.put_object(
                        Bucket=self._bucket, Key=validated, Body=data, ContentType=content_type
                    )
                )
                return
            if buffer:
                parts.append(await self._upload_part(validated, upload_id, len(parts) + 1, buffer))
            finished_id = upload_id
            await self._call(
                lambda: self._client.complete_multipart_upload(
                    Bucket=self._bucket,
                    Key=validated,
                    UploadId=finished_id,
                    MultipartUpload={"Parts": parts},  # type: ignore[typeddict-item]
                )
            )
        except BaseException:
            if upload_id is not None:
                await asyncio.shield(self._abort(validated, upload_id))
            raise

    def read_chunks(self, key: str) -> Iterator[bytes]:
        validated = validate_key(key)
        try:
            body = self._client.get_object(Bucket=self._bucket, Key=validated)["Body"]
            try:
                yield from body.iter_chunks(chunk_size=READ_CHUNK_BYTES)
            finally:
                body.close()
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in MISSING_OBJECT_CODES:
                raise ObjectNotFoundError(f"no object with key {key}") from error
            raise ObjectStorageError(f"object storage request failed: {error}") from error
        except BotoCoreError as error:
            raise ObjectStorageError(f"object storage request failed: {error}") from error

    async def delete(self, key: str) -> None:
        validated = validate_key(key)

        def remove() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=validated)

        await self._call(remove)

    async def _upload_part(
        self, key: str, upload_id: str, number: int, buffer: bytearray
    ) -> dict[str, str | int]:
        body = bytes(buffer[: self._part_size])
        response = await self._call(
            lambda: self._client.upload_part(
                Bucket=self._bucket, Key=key, UploadId=upload_id, PartNumber=number, Body=body
            )
        )
        return {"ETag": response["ETag"], "PartNumber": number}

    async def _abort(self, key: str, upload_id: str) -> None:
        try:
            await self._call(
                lambda: self._client.abort_multipart_upload(
                    Bucket=self._bucket, Key=key, UploadId=upload_id
                )
            )
        except ObjectStorageError:
            return

    async def _call[ResultT](self, operation: Callable[[], ResultT]) -> ResultT:
        try:
            return await asyncio.to_thread(operation)
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageError(f"object storage request failed: {error}") from error

    def public_url(self, key: str) -> str:
        return build_public_url(self._public_base_url, key)
