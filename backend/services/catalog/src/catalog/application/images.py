import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from catalog.application.errors import (
    InvalidUploadError,
    PreconditionFailedError,
    ProductImageNotFoundError,
    ProductNotFoundError,
    UnsupportedMediaError,
)
from catalog.application.ports import ImageProcessor, ImageRenditions, UnitOfWorkFactory
from catalog.application.products import lock_and_check, require_sku, utc_now
from catalog.domain.image import (
    IMMUTABLE_CACHE_CONTROL,
    RENDITION_CONTENT_TYPE,
    SIGNATURE_LENGTH,
    detect_image_format,
    full_key,
    new_image_key,
    thumbnail_key,
)
from catalog.domain.preconditions import VersionPrecondition
from catalog.domain.product import Product
from ecommerce_storage import ObjectStorage

logger = logging.getLogger(__name__)

MAX_PARALLEL_RENDERS = 2
EMPTY_UPLOAD = "empty_file"


class ImageService:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        processor: ImageProcessor,
        storage: ObjectStorage,
        clock: Callable[[], datetime] = utc_now,
        new_id: Callable[[], UUID] = uuid4,
        max_parallel_renders: int = MAX_PARALLEL_RENDERS,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._processor = processor
        self._storage = storage
        self._clock = clock
        self._new_id = new_id
        self._renders = asyncio.Semaphore(max_parallel_renders)

    async def verify(self, sku: str, precondition: VersionPrecondition) -> None:
        normalized = require_sku(sku)
        async with self._unit_of_work() as uow:
            current = await uow.products.get(normalized)
        if current is None:
            raise ProductNotFoundError(normalized)
        if not precondition.satisfied_by(current.version):
            raise PreconditionFailedError(normalized)

    async def replace(self, sku: str, data: bytes, precondition: VersionPrecondition) -> Product:
        normalized = require_sku(sku)
        await self.verify(normalized, precondition)
        if not data:
            raise InvalidUploadError(EMPTY_UPLOAD, "the file is empty")
        if detect_image_format(data[:SIGNATURE_LENGTH]) is None:
            raise UnsupportedMediaError("only JPEG, PNG and WebP images are accepted")
        renditions = await self._render(data)
        image_key = new_image_key(normalized, self._new_id())
        new_keys = [thumbnail_key(image_key), full_key(image_key)]
        try:
            await self._store(image_key, renditions)
            async with self._unit_of_work() as uow:
                current = await lock_and_check(uow, normalized, precondition)
                product = await uow.products.set_image(normalized, image_key, self._clock())
                await uow.commit()
        except BaseException:
            await asyncio.shield(self._discard(new_keys))
            raise
        await self._discard(_keys_of(current.image_key))
        return product

    async def remove(self, sku: str, precondition: VersionPrecondition) -> Product:
        normalized = require_sku(sku)
        async with self._unit_of_work() as uow:
            current = await lock_and_check(uow, normalized, precondition)
            if current.image_key is None:
                raise ProductImageNotFoundError(normalized)
            product = await uow.products.set_image(normalized, None, self._clock())
            await uow.commit()
        await self._discard(_keys_of(current.image_key))
        return product

    async def _render(self, data: bytes) -> ImageRenditions:
        async with self._renders:
            return await asyncio.to_thread(self._processor.render, data)

    async def _store(self, image_key: str, renditions: ImageRenditions) -> None:
        await self._storage.put(
            thumbnail_key(image_key),
            renditions.thumbnail,
            RENDITION_CONTENT_TYPE,
            IMMUTABLE_CACHE_CONTROL,
        )
        await self._storage.put(
            full_key(image_key), renditions.full, RENDITION_CONTENT_TYPE, IMMUTABLE_CACHE_CONTROL
        )

    async def _discard(self, keys: list[str]) -> None:
        for key in keys:
            try:
                await self._storage.delete(key)
            except Exception:
                logger.warning("image cleanup failed, object left orphaned", extra={"key": key})


def _keys_of(image_key: str | None) -> list[str]:
    return [thumbnail_key(image_key), full_key(image_key)] if image_key is not None else []
