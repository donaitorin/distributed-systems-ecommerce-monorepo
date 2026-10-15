import io
import struct
import zlib

from PIL import ExifTags, Image, ImageCms

from catalog.domain.image import PNG_SIGNATURE

LEFT_COLOR = (220, 20, 20)
RIGHT_COLOR = (20, 20, 220)


def two_tone(size: tuple[int, int], mode: str = "RGB") -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, RIGHT_COLOR)
    image.paste(LEFT_COLOR, (0, 0, width // 2, height))
    return image.convert(mode)


def encode(image: Image.Image, image_format: str, **options: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


def jpeg(size: tuple[int, int] = (800, 600)) -> bytes:
    return encode(two_tone(size), "JPEG", quality=90)


def png(size: tuple[int, int] = (800, 600), mode: str = "RGB") -> bytes:
    return encode(two_tone(size, mode), "PNG")


def webp(size: tuple[int, int] = (800, 600)) -> bytes:
    return encode(two_tone(size), "WEBP")


def jpeg_with_metadata(orientation: int, size: tuple[int, int] = (800, 600)) -> bytes:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    exif[ExifTags.Base.Make] = "Secret Camera Co"
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps[ExifTags.GPS.GPSLatitude] = (40.0, 26.0, 46.0)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return encode(two_tone(size), "JPEG", exif=exif, icc_profile=profile)


def transparent_png(size: tuple[int, int] = (200, 100)) -> bytes:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.paste((10, 200, 10, 255), (size[0] // 2, 0, size[0], size[1]))
    return encode(image, "PNG")


def palette_png_with_transparency(size: tuple[int, int] = (64, 64)) -> bytes:
    image = Image.new("P", size, 0)
    image.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
    image.paste(1, (0, 0, size[0] // 2, size[1]))
    return encode(image, "PNG", transparency=0)


def animated_webp(size: tuple[int, int] = (120, 80)) -> bytes:
    frames = [Image.new("RGB", size, color) for color in ((255, 0, 0), (0, 255, 0))]
    return encode(frames[0], "WEBP", save_all=True, append_images=frames[1:], duration=100)


def png_declaring(width: int, height: int) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )


def multipart(
    parts: list[tuple[str, str, bytes, str]], boundary: str = "test-boundary"
) -> tuple[bytes, str]:
    body = b""
    for name, filename, content, content_type in parts:
        body += (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
            ).encode()
            + content
            + b"\r\n"
        )
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"
