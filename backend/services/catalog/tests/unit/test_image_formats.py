import pytest
from catalog_testing import images

from catalog.domain.image import ImageFormat, detect_image_format, full_key, thumbnail_key


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (images.jpeg(), ImageFormat.JPEG),
        (images.png(), ImageFormat.PNG),
        (images.webp(), ImageFormat.WEBP),
        (b"\xff\xd8\xff\xe0garbage", ImageFormat.JPEG),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ImageFormat.WEBP),
    ],
)
def test_supported_formats_are_recognised_by_their_first_bytes(
    data: bytes, expected: ImageFormat
) -> None:
    assert detect_image_format(data[:12]) is expected


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"hello world, this is plain text",
        b"<html><body>not an image</body></html>",
        b"GIF89a\x01\x00\x01\x00",
        b"BM\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
        b"%PDF-1.7\n",
        b"RIFF\x00\x00\x00\x00WAVEfmt ",
        b"\xff\xd8",
        b"\x89PNG",
    ],
)
def test_everything_else_is_rejected(data: bytes) -> None:
    assert detect_image_format(data) is None


def test_renditions_share_the_key_stem() -> None:
    assert thumbnail_key("products/A-1/abc") == "products/A-1/abc-400.webp"
    assert full_key("products/A-1/abc") == "products/A-1/abc-1200.webp"
