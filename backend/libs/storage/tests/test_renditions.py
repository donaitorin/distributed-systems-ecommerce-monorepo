import pytest

from ecommerce_storage import (
    FULL_SUFFIX,
    THUMBNAIL_SUFFIX,
    build_public_url,
    full_key,
    image_key_from_full_url,
    key_from_public_url,
    thumbnail_key,
)

BASE = "/media"
IMAGE_KEY = "products/RS-001/0b9c5d7e-1a02-4f7e-8a21-3f2b8c1e6d4a"


def test_rendition_keys_extend_the_image_key() -> None:
    assert thumbnail_key(IMAGE_KEY) == IMAGE_KEY + "-400.webp"
    assert full_key(IMAGE_KEY) == IMAGE_KEY + "-1200.webp"
    assert (THUMBNAIL_SUFFIX, FULL_SUFFIX) == ("-400.webp", "-1200.webp")


@pytest.mark.parametrize("base", ["/media", "/media/", "http://localhost:8000/media"])
def test_a_public_url_maps_back_to_its_key(base: str) -> None:
    url = build_public_url(base, "products/A B/ü.webp")

    assert key_from_public_url(base, url) == "products/A B/ü.webp"


@pytest.mark.parametrize(
    "url", ["/other/products/x.webp", "/media/", "/media", "/media/../secret", "/media//x"]
)
def test_a_url_outside_the_base_or_with_a_bad_key_has_no_key(url: str) -> None:
    assert key_from_public_url(BASE, url) is None


def test_the_image_key_is_recovered_from_the_full_rendition_url() -> None:
    url = build_public_url(BASE, full_key(IMAGE_KEY))

    assert image_key_from_full_url(BASE, url) == IMAGE_KEY


@pytest.mark.parametrize(
    "url",
    [
        "/media/products/RS-001/x-400.webp",
        "/media/-1200.webp",
        "/elsewhere/products/RS-001/x-1200.webp",
    ],
)
def test_other_urls_do_not_yield_an_image_key(url: str) -> None:
    assert image_key_from_full_url(BASE, url) is None
