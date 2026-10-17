from cart.application.ports import ProductProjection
from cart.domain.product import ProductState
from ecommerce_contracts import Envelope, ProductDeletedV1, ProductUpdatedV1


class ProjectionUpdates:
    def __init__(self, projection: ProductProjection) -> None:
        self._projection = projection

    async def updated(self, envelope: Envelope[ProductUpdatedV1]) -> None:
        payload = envelope.payload
        await self._projection.apply_state(
            ProductState(
                sku=payload.sku,
                name=payload.name,
                price=payload.price,
                stock=payload.stock,
                version=payload.version,
                deleted=False,
                image_key=payload.image_key,
            )
        )

    async def deleted(self, envelope: Envelope[ProductDeletedV1]) -> None:
        payload = envelope.payload
        await self._projection.apply_deletion(payload.sku, payload.version)
