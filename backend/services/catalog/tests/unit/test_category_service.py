import pytest

from catalog.application.categories import CategoryService
from catalog.application.errors import DuplicateCategoryError
from catalog.domain.errors import ValidationFailedError
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork


@pytest.fixture
def service(store: InMemoryStore) -> CategoryService:
    return CategoryService(lambda: InMemoryUnitOfWork(store))


async def test_list_is_sorted_by_name_ignoring_case(service: CategoryService) -> None:
    await service.create("aardvark supplies")

    names = [item.name for item in await service.list_all()]

    assert names == ["aardvark supplies", "Books", "Electronics", "Home & Office"]


async def test_create_derives_the_slug_and_normalizes_the_name(service: CategoryService) -> None:
    category = await service.create("  Pet   Supplies ")

    assert (category.name, category.slug) == ("Pet Supplies", "pet-supplies")
    assert category in await service.list_all()


@pytest.mark.parametrize("name", ["electronics", "ELECTRONICS", "  Electronics  "])
async def test_duplicate_names_are_rejected_ignoring_case_and_spaces(
    service: CategoryService, name: str
) -> None:
    with pytest.raises(DuplicateCategoryError):
        await service.create(name)


async def test_names_with_the_same_slug_are_rejected(service: CategoryService) -> None:
    with pytest.raises(DuplicateCategoryError):
        await service.create("Home Office")


@pytest.mark.parametrize("name", ["", "   ", "!!!"])
async def test_invalid_names_are_rejected(service: CategoryService, name: str) -> None:
    with pytest.raises(ValidationFailedError):
        await service.create(name)
