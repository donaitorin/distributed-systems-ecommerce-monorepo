import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from catalog.application.errors import InvalidUploadError
from catalog.application.ports import ImageRenditions
from catalog.domain.image import FULL_SIZE, MAX_PIXELS, THUMBNAIL_SIZE, ImageFormat

WEBP_QUALITY = 82
WEBP_METHOD = 4
ALPHA_MODES = frozenset({"RGBA", "LA", "PA"})
INVALID_IMAGE = "invalid_image"
IMAGE_TOO_LARGE = "image_too_large"

Image.MAX_IMAGE_PIXELS = MAX_PIXELS
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)


class PillowImageProcessor:
    def render(self, data: bytes) -> ImageRenditions:
        try:
            with Image.open(io.BytesIO(data)) as source:
                self._require_supported(source)
                source.load()
                upright = ImageOps.exif_transpose(source)
                image = self._normalize(upright)
                return ImageRenditions(
                    thumbnail=self._encode(image, THUMBNAIL_SIZE),
                    full=self._encode(image, FULL_SIZE),
                )
        except Image.DecompressionBombError as error:
            raise InvalidUploadError(IMAGE_TOO_LARGE, _too_many_pixels()) from error
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as error:
            raise InvalidUploadError(INVALID_IMAGE, "the file is not a readable image") from error

    @staticmethod
    def _require_supported(source: Image.Image) -> None:
        if source.format not in {item.value for item in ImageFormat}:
            raise InvalidUploadError(INVALID_IMAGE, "the file is not a JPEG, PNG or WebP image")
        width, height = source.size
        if width * height > MAX_PIXELS:
            raise InvalidUploadError(IMAGE_TOO_LARGE, _too_many_pixels())

    @staticmethod
    def _normalize(image: Image.Image) -> Image.Image:
        has_alpha = image.mode in ALPHA_MODES or (
            image.mode == "P" and "transparency" in image.info
        )
        converted = image.convert("RGBA" if has_alpha else "RGB")
        converted.info = {}
        return converted

    @staticmethod
    def _encode(image: Image.Image, longest_side: int) -> bytes:
        rendition = image.copy()
        rendition.thumbnail((longest_side, longest_side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        rendition.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
        return buffer.getvalue()


def _too_many_pixels() -> str:
    return f"the image must have at most {MAX_PIXELS:,} pixels"
