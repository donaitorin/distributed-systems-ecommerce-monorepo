from typing import Final

from ecommerce_storage.urls import key_from_public_url

THUMBNAIL_SUFFIX: Final = "-400.webp"
FULL_SUFFIX: Final = "-1200.webp"


def thumbnail_key(image_key: str) -> str:
    return image_key + THUMBNAIL_SUFFIX


def full_key(image_key: str) -> str:
    return image_key + FULL_SUFFIX


def image_key_from_full_url(public_base_url: str, url: str) -> str | None:
    key = key_from_public_url(public_base_url, url)
    if key is None or not key.endswith(FULL_SUFFIX):
        return None
    return key.removesuffix(FULL_SUFFIX) or None
