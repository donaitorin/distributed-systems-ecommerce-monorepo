from catalog.domain.image import full_key, thumbnail_key
from ecommerce_storage import ObjectStorage


class MediaUrls:
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    def image(self, image_key: str | None) -> str | None:
        return self._storage.public_url(full_key(image_key)) if image_key is not None else None

    def thumbnail(self, image_key: str | None) -> str | None:
        return self._storage.public_url(thumbnail_key(image_key)) if image_key is not None else None
