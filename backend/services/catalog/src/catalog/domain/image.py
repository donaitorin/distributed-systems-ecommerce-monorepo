from enum import StrEnum
from typing import Final
from uuid import UUID

MAX_UPLOAD_BYTES: Final = 5 * 1024 * 1024
MAX_PIXELS: Final = 25_000_000
THUMBNAIL_SIZE: Final = 400
FULL_SIZE: Final = 1200
THUMBNAIL_SUFFIX: Final = "-400.webp"
FULL_SUFFIX: Final = "-1200.webp"
RENDITION_CONTENT_TYPE: Final = "image/webp"
IMMUTABLE_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"
SIGNATURE_LENGTH: Final = 12

PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE: Final = b"\xff\xd8\xff"


class ImageFormat(StrEnum):
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"


def detect_image_format(head: bytes) -> ImageFormat | None:
    if head.startswith(JPEG_SIGNATURE):
        return ImageFormat.JPEG
    if head.startswith(PNG_SIGNATURE):
        return ImageFormat.PNG
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ImageFormat.WEBP
    return None


def new_image_key(sku: str, identifier: UUID) -> str:
    return f"products/{sku}/{identifier}"


def thumbnail_key(image_key: str) -> str:
    return image_key + THUMBNAIL_SUFFIX


def full_key(image_key: str) -> str:
    return image_key + FULL_SUFFIX
