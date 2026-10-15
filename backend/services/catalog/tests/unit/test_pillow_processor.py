import io
import time

import pytest
from catalog_testing import images
from catalog_testing.images import LEFT_COLOR, RIGHT_COLOR
from PIL import Image

from catalog.application.errors import InvalidUploadError
from catalog.infra.imaging import IMAGE_TOO_LARGE, INVALID_IMAGE, PillowImageProcessor

processor = PillowImageProcessor()


def open_webp(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def pixel(image: Image.Image, position: tuple[int, int]) -> tuple[int, ...]:
    value = image.getpixel(position)
    assert isinstance(value, tuple)
    return value


def close(actual: tuple[int, ...], expected: tuple[int, ...], tolerance: int = 40) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(actual, expected, strict=False))


@pytest.mark.parametrize(
    "data", [images.jpeg(), images.png(), images.webp()], ids=["jpeg", "png", "webp"]
)
def test_every_supported_format_becomes_two_webp_renditions(data: bytes) -> None:
    renditions = processor.render(data)

    thumbnail, full = open_webp(renditions.thumbnail), open_webp(renditions.full)
    assert thumbnail.format == full.format == "WEBP"
    assert thumbnail.size == (400, 300)
    assert full.size == (800, 600)


def test_large_images_are_fitted_to_the_longest_side_keeping_the_aspect() -> None:
    renditions = processor.render(images.jpeg((3000, 2000)))

    assert open_webp(renditions.thumbnail).size == (400, 267)
    assert open_webp(renditions.full).size == (1200, 800)


def test_portrait_images_are_limited_by_their_height() -> None:
    renditions = processor.render(images.jpeg((1000, 3000)))

    assert open_webp(renditions.thumbnail).size == (133, 400)
    assert open_webp(renditions.full).size == (400, 1200)


def test_small_images_are_never_upscaled() -> None:
    renditions = processor.render(images.png((100, 50)))

    assert open_webp(renditions.thumbnail).size == (100, 50)
    assert open_webp(renditions.full).size == (100, 50)


def test_exif_orientation_is_applied_to_the_pixels() -> None:
    renditions = processor.render(images.jpeg_with_metadata(orientation=6, size=(800, 600)))

    full = open_webp(renditions.full).convert("RGB")
    assert full.size == (600, 800)
    assert close(pixel(full, (300, 100)), LEFT_COLOR)
    assert close(pixel(full, (300, 700)), RIGHT_COLOR)


@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_orientation_never_leaks_into_the_output(orientation: int) -> None:
    renditions = processor.render(images.jpeg_with_metadata(orientation))

    for data in (renditions.thumbnail, renditions.full):
        assert not open_webp(data).getexif()


def test_exif_gps_and_icc_profiles_are_removed_from_the_output() -> None:
    source = images.jpeg_with_metadata(orientation=1)
    assert b"Secret Camera Co" in source
    assert b"ICC_PROFILE" in source

    renditions = processor.render(source)

    for data in (renditions.thumbnail, renditions.full):
        decoded = open_webp(data)
        assert not decoded.getexif()
        assert "icc_profile" not in decoded.info
        assert "exif" not in decoded.info
        assert "xmp" not in decoded.info
        for marker in (b"EXIF", b"ICCP", b"XMP ", b"Secret Camera Co", b"sRGB"):
            assert marker not in data


def test_transparency_is_preserved() -> None:
    renditions = processor.render(images.transparent_png())

    decoded = open_webp(renditions.full)
    assert decoded.mode == "RGBA"
    assert pixel(decoded, (10, 50))[3] == 0
    assert pixel(decoded, (150, 50))[3] == 255


def test_palette_images_with_transparency_keep_their_alpha() -> None:
    decoded = open_webp(processor.render(images.palette_png_with_transparency()).full)

    assert decoded.mode == "RGBA"
    assert pixel(decoded, (50, 10))[3] == 0


@pytest.mark.parametrize("mode", ["L", "1", "CMYK"])
def test_other_color_modes_become_rgb(mode: str) -> None:
    source = images.encode(images.two_tone((120, 80), mode), "PNG" if mode != "CMYK" else "JPEG")

    decoded = open_webp(processor.render(source).full)

    assert decoded.mode == "RGB"
    assert decoded.size == (120, 80)


def test_animated_images_keep_only_their_first_frame() -> None:
    decoded = open_webp(processor.render(images.animated_webp()).full)

    assert getattr(decoded, "n_frames", 1) == 1
    assert close(pixel(decoded.convert("RGB"), (10, 10)), (255, 0, 0))


def test_an_image_with_too_many_pixels_is_refused_before_decoding() -> None:
    forged = images.png_declaring(5001, 5000)

    started = time.perf_counter()
    with pytest.raises(InvalidUploadError) as raised:
        processor.render(forged)

    assert raised.value.code == IMAGE_TOO_LARGE
    assert time.perf_counter() - started < 1


def test_a_decompression_bomb_is_refused() -> None:
    forged = images.png_declaring(60_000, 60_000)

    with pytest.raises(InvalidUploadError) as raised:
        processor.render(forged)

    assert raised.value.code == IMAGE_TOO_LARGE


@pytest.mark.parametrize(
    "data",
    [
        images.jpeg()[:200],
        images.png()[:60],
        b"\x89PNG\r\n\x1a\n" + b"not really a png",
        b"\xff\xd8\xff\xe0" + b"junk" * 50,
        b"RIFF\x10\x00\x00\x00WEBPjunkjunk",
    ],
    ids=["truncated-jpeg", "truncated-png", "fake-png", "fake-jpeg", "fake-webp"],
)
def test_corrupt_files_with_a_valid_signature_are_invalid_images(data: bytes) -> None:
    with pytest.raises(InvalidUploadError) as raised:
        processor.render(data)

    assert raised.value.code == INVALID_IMAGE


def test_formats_pillow_can_read_but_we_do_not_accept_are_refused() -> None:
    gif = images.encode(images.two_tone((20, 20)), "GIF")

    with pytest.raises(InvalidUploadError) as raised:
        processor.render(gif)

    assert raised.value.code == INVALID_IMAGE
