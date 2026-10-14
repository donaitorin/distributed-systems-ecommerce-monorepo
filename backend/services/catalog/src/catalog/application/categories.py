from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.product import Category
from catalog.domain.slug import build_category


class CategoryService:
    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    async def list_all(self) -> list[Category]:
        async with self._unit_of_work() as uow:
            return await uow.categories.list_all()

    async def create(self, raw_name: str) -> Category:
        name, slug = build_category(raw_name)
        async with self._unit_of_work() as uow:
            category = await uow.categories.add(name, slug)
            await uow.commit()
        return category
