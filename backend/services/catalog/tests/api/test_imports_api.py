import csv
import io
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from catalog_testing import images
from catalog_testing.csv_import import csv_text, row
from catalog_testing.imports import SAMPLE, store_with_categories
from catalog_testing.support import SteppingClock, build_test_app, http_client

from catalog.application.import_jobs import ImportJobs
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from ecommerce_auth.testing import StubTokenIssuer
from ecommerce_storage import InMemoryObjectStorage

IMPORTS = "/api/v1/imports"


@pytest.fixture
def store() -> InMemoryStore:
    return store_with_categories()


@pytest.fixture
def jobs(
    store: InMemoryStore, imports_storage: InMemoryObjectStorage, clock: SteppingClock
) -> ImportJobs:
    return ImportJobs(lambda: InMemoryUnitOfWork(store), imports_storage, clock)


def multipart_upload(
    data: bytes, filename: str = "products.csv", field: str = "file"
) -> dict[str, Any]:
    body, content_type = images.multipart([(field, filename, data, "text/csv")])
    return {"content": body, "headers": {"Content-Type": content_type}}


async def upload(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    data: bytes = SAMPLE,
    filename: str = "products.csv",
) -> httpx.Response:
    request = multipart_upload(data, filename)
    return await client.post(
        IMPORTS, content=request["content"], headers=admin | request["headers"]
    )


async def uploaded_and_validated(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs, data: bytes = SAMPLE
) -> dict[str, Any]:
    created = (await upload(client, admin, data)).json()
    await jobs.validate(UUID(created["id"]))
    body: dict[str, Any] = (await client.get(f"{IMPORTS}/{created['id']}", headers=admin)).json()
    return body


async def test_uploading_a_csv_returns_202_with_the_import_and_its_links(
    client: httpx.AsyncClient, admin: dict[str, str], imports_storage: InMemoryObjectStorage
) -> None:
    response = await upload(client, admin, filename="catalog-october.csv")

    body = response.json()
    assert response.status_code == 202
    assert response.headers["Location"] == f"{IMPORTS}/{body['id']}"
    assert body["status"] == "uploaded"
    assert body["filename"] == "catalog-october.csv"
    assert body["size_bytes"] == len(SAMPLE)
    assert len(body["sha256"]) == 64
    assert body["created_by"]
    assert body["summary"] is None
    assert body["problems"] == []
    assert body["links"] == {
        "self": f"{IMPORTS}/{body['id']}",
        "problems": f"{IMPORTS}/{body['id']}/problems",
        "problems_csv": f"{IMPORTS}/{body['id']}/problems.csv",
        "confirm": None,
    }
    assert len(imports_storage.keys()) == 1


async def test_the_same_file_uploaded_again_returns_the_existing_import_with_200(
    client: httpx.AsyncClient, admin: dict[str, str], imports_storage: InMemoryObjectStorage
) -> None:
    first = await upload(client, admin)

    second = await upload(client, admin, filename="again.csv")

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["filename"] == first.json()["filename"]
    assert len(imports_storage.keys()) == 1


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", IMPORTS),
        ("GET", f"{IMPORTS}/{uuid4()}"),
        ("GET", f"{IMPORTS}/{uuid4()}/problems"),
        ("GET", f"{IMPORTS}/{uuid4()}/problems.csv"),
        ("POST", f"{IMPORTS}/{uuid4()}/confirm"),
    ],
)
async def test_the_import_endpoints_need_a_token(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    assert (await client.request(method, path)).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", IMPORTS),
        ("GET", f"{IMPORTS}/{uuid4()}"),
        ("GET", f"{IMPORTS}/{uuid4()}/problems"),
        ("GET", f"{IMPORTS}/{uuid4()}/problems.csv"),
        ("POST", f"{IMPORTS}/{uuid4()}/confirm"),
    ],
)
async def test_customers_cannot_use_the_import_endpoints(
    client: httpx.AsyncClient, customer: dict[str, str], method: str, path: str
) -> None:
    response = await client.request(method, path, headers=customer)

    assert response.status_code == 403


async def test_a_body_that_is_not_multipart_is_a_415(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.post(
        IMPORTS, content=SAMPLE, headers=admin | {"Content-Type": "text/csv"}
    )

    assert response.status_code == 415
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_missing_file_part_is_a_422_and_nothing_is_stored(
    client: httpx.AsyncClient, admin: dict[str, str], imports_storage: InMemoryObjectStorage
) -> None:
    request = multipart_upload(SAMPLE, field="document")

    response = await client.post(
        IMPORTS, content=request["content"], headers=admin | request["headers"]
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "missing_file"
    assert imports_storage.keys() == []


async def test_an_incomplete_multipart_body_is_a_422(
    client: httpx.AsyncClient, admin: dict[str, str], imports_storage: InMemoryObjectStorage
) -> None:
    request = multipart_upload(SAMPLE)
    truncated = request["content"][:200]

    response = await client.post(IMPORTS, content=truncated, headers=admin | request["headers"])

    assert response.status_code == 422
    assert imports_storage.keys() == []


async def test_a_garbled_multipart_body_is_a_422(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.post(
        IMPORTS,
        content=b"--wrong\r\nnot multipart at all",
        headers=admin | {"Content-Type": "multipart/form-data; boundary=right"},
    )

    assert response.status_code == 422


@pytest.fixture
async def small_client(
    issuer: StubTokenIssuer,
    store: InMemoryStore,
    clock: SteppingClock,
    imports_storage: InMemoryObjectStorage,
) -> AsyncIterator[httpx.AsyncClient]:
    app = build_test_app(
        issuer,
        lambda: InMemoryUnitOfWork(store),
        clock,
        imports_storage=imports_storage,
        import_max_bytes=2 * 1024 * 1024,
    )
    async with http_client(app) as client:
        yield client


async def test_a_file_over_the_limit_is_a_413_and_is_not_read_to_the_end(
    small_client: httpx.AsyncClient,
    admin: dict[str, str],
    imports_storage: InMemoryObjectStorage,
) -> None:
    sent = 0
    chunk = b"a,b,c\n" * (256 * 1024 // 6)

    async def endless() -> AsyncIterator[bytes]:
        nonlocal sent
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n\r\n'
        for _ in range(500):
            sent += 1
            yield chunk
        yield b"\r\n--b--\r\n"

    response = await small_client.post(
        IMPORTS,
        content=endless(),
        headers=admin | {"Content-Type": "multipart/form-data; boundary=b"},
    )

    assert response.status_code == 413
    assert response.json()["title"] == "File too large"
    assert "2 MB" in response.json()["detail"]
    assert sent < 20
    assert imports_storage.keys() == []


async def test_a_declared_length_over_the_limit_is_refused_before_reading(
    small_client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    request = multipart_upload(SAMPLE)

    response = await small_client.post(
        IMPORTS,
        content=request["content"],
        headers=admin | request["headers"] | {"Content-Length": str(50 * 1024 * 1024)},
    )

    assert response.status_code == 413


async def test_getting_an_unknown_import_is_a_404(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.get(f"{IMPORTS}/{uuid4()}", headers=admin)

    assert response.status_code == 404
    assert response.json()["title"] == "Import not found"


async def test_an_id_that_is_not_a_uuid_is_a_422(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.get(f"{IMPORTS}/not-a-uuid", headers=admin)

    assert response.status_code == 422
    assert response.json()["errors"][0]["location"] == "path.import_id"


async def test_a_validated_import_exposes_the_report(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)

    assert body["status"] == "validated"
    assert body["summary"] == {
        "rejected": False,
        "rows_read": 97,
        "blank_rows": 2,
        "error_rows": 4,
        "error_count": 4,
        "warning_count": 3,
        "superseded_rows": 2,
        "duplicate_rows": 1,
        "importable_rows": 88,
        "to_create": 88,
        "to_update": 0,
        "to_restore": 0,
        "unchanged": 0,
        "truncated": False,
        "unknown_categories": [],
    }
    assert [(item["row"], item["severity"]) for item in body["problems"]] == [
        (7, "error"),
        (16, "error"),
        (25, "error"),
        (41, "error"),
        (2, "warning"),
        (4, "warning"),
        (56, "warning"),
    ]
    assert body["problems"][0] == {
        "severity": "error",
        "row": 7,
        "column": "price",
        "value": "free",
        "code": "not_a_number",
        "reason": "price must be a plain number such as 29.99",
    }
    assert body["links"]["confirm"] == f"{IMPORTS}/{body['id']}/confirm"


async def test_nothing_reaches_the_catalog_before_confirmation(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    await uploaded_and_validated(client, admin, jobs)

    listing = (await client.get("/api/v1/products")).json()

    assert listing["total"] == 0


async def test_the_problems_endpoint_pages_with_a_cursor_and_filters_by_severity(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)
    url = f"{IMPORTS}/{body['id']}/problems"

    errors = (await client.get(url, params={"severity": "error"}, headers=admin)).json()
    first = (await client.get(url, params={"limit": 25}, headers=admin)).json()

    assert [item["row"] for item in errors["items"]] == [7, 16, 25, 41]
    assert errors["next_cursor"] is None
    assert len(first["items"]) == 7
    assert first["next_cursor"] is None


async def test_the_problems_endpoint_follows_the_cursor_across_pages(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    content = csv_text(*(row(sku=f"S-{number}", name="") for number in range(60))).encode()
    body = await uploaded_and_validated(client, admin, jobs, content)
    url = f"{IMPORTS}/{body['id']}/problems"

    first = (await client.get(url, params={"limit": 25}, headers=admin)).json()
    second = (
        await client.get(url, params={"limit": 25, "cursor": first["next_cursor"]}, headers=admin)
    ).json()
    third = (
        await client.get(url, params={"limit": 25, "cursor": second["next_cursor"]}, headers=admin)
    ).json()

    rows = [item["row"] for page in (first, second, third) for item in page["items"]]
    assert rows == list(range(2, 62))
    assert third["next_cursor"] is None


@pytest.mark.parametrize(
    ("params", "location"),
    [
        ({"severity": "info"}, "query.severity"),
        ({"limit": "7"}, "query.limit"),
        ({"limit": "abc"}, "query.limit"),
        ({"cursor": "garbage!"}, "query.cursor"),
    ],
)
async def test_invalid_problem_parameters_are_422_problems(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    jobs: ImportJobs,
    params: dict[str, str],
    location: str,
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)

    response = await client.get(f"{IMPORTS}/{body['id']}/problems", params=params, headers=admin)

    assert response.status_code == 422
    assert location in [item["location"] for item in response.json()["errors"]]


async def test_the_problems_of_an_unknown_import_are_a_404(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.get(f"{IMPORTS}/{uuid4()}/problems", headers=admin)

    assert response.status_code == 404


async def test_the_problems_can_be_downloaded_as_a_csv(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)

    response = await client.get(f"{IMPORTS}/{body['id']}/problems.csv", headers=admin)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="import-{body["id"]}-problems.csv"'
    )
    text = response.content.decode()
    assert text.startswith("﻿severity,row,column,value,code,reason\r\n")
    rows = list(csv.reader(io.StringIO(text.removeprefix("﻿"))))
    assert len(rows) == 8
    assert rows[3][1:5] == ["7", "price", "free", "not_a_number"]


async def test_downloading_the_problems_of_an_unknown_import_is_a_404(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.get(f"{IMPORTS}/{uuid4()}/problems.csv", headers=admin)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_rejected_file_reports_its_document_problems(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs, b"colour,size\r\nred,10\r\n")

    assert body["status"] == "rejected"
    assert body["summary"]["rejected"] is True
    assert body["links"]["confirm"] is None
    assert {item["code"] for item in body["problems"]} == {"missing_column", "unknown_column"}
    assert all(item["row"] == 1 for item in body["problems"])


async def test_a_text_file_renamed_to_csv_is_stored_and_then_rejected_by_validation(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs, b"\x89PNG\r\n\x1a\n\x00\x00")

    assert body["status"] == "rejected"
    assert [item["code"] for item in body["problems"]] == ["not_text"]


async def test_confirming_before_validation_finishes_is_a_409(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    created = (await upload(client, admin)).json()

    response = await client.post(f"{IMPORTS}/{created['id']}/confirm", headers=admin)

    assert response.status_code == 409
    assert response.json()["title"] == "Import cannot be confirmed"
    assert response.json()["import_status"] == "uploaded"
    assert "not been validated" in response.json()["detail"]


async def test_confirming_a_rejected_import_is_a_409(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs, b"colour\r\nred\r\n")

    response = await client.post(f"{IMPORTS}/{body['id']}/confirm", headers=admin)

    assert response.status_code == 409
    assert response.json()["import_status"] == "rejected"


async def test_confirming_an_unknown_import_is_a_404(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    assert (await client.post(f"{IMPORTS}/{uuid4()}/confirm", headers=admin)).status_code == 404


async def test_confirming_a_validated_import_answers_202_and_is_idempotent(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs, store: InMemoryStore
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)

    first = await client.post(f"{IMPORTS}/{body['id']}/confirm", headers=admin)
    second = await client.post(f"{IMPORTS}/{body['id']}/confirm", headers=admin)

    assert first.status_code == second.status_code == 202
    assert first.json()["status"] == "queued"
    assert first.json()["confirmed_at"] is not None
    assert first.json()["links"]["confirm"] is None
    requests = [item for item in store.import_data.outbox if item.event_type == "import.requested"]
    assert len(requests) == 1
    assert store.products == {}


async def test_after_processing_the_import_is_completed_and_the_products_exist(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)
    await client.post(f"{IMPORTS}/{body['id']}/confirm", headers=admin)
    await jobs.process(UUID(body["id"]))

    finished = (await client.get(f"{IMPORTS}/{body['id']}", headers=admin)).json()
    sql = await client.get("/api/v1/products/SQL-001")
    script = await client.get("/api/v1/products/XS-001")
    listing = (await client.get("/api/v1/products")).json()

    assert finished["status"] == "completed"
    assert finished["finished_at"] is not None
    assert finished["progress"] == {
        "processed_rows": 88,
        "created_rows": 88,
        "updated_rows": 0,
        "restored_rows": 0,
        "unchanged_rows": 0,
    }
    assert sql.json()["name"] == "Robert'); DROP TABLE products;--"
    assert script.json()["name"] == "<script>alert('xss')</script>"
    assert listing["total"] == 88


async def test_a_deleted_product_comes_back_through_an_import(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    content = csv_text(row(sku="RS-001")).encode()
    created = await client.post(
        "/api/v1/products",
        json={"sku": "RS-001", "name": "Old", "price": "1.00", "stock": 1},
        headers=admin,
    )
    await client.delete("/api/v1/products/RS-001", headers=admin | {"If-Match": "*"})
    again = await client.post(
        "/api/v1/products",
        json={"sku": "RS-001", "name": "Old", "price": "1.00", "stock": 1},
        headers=admin,
    )
    body = await uploaded_and_validated(client, admin, jobs, content)
    await client.post(f"{IMPORTS}/{body['id']}/confirm", headers=admin)
    await jobs.process(UUID(body["id"]))

    restored = await client.get("/api/v1/products/RS-001")

    assert created.status_code == 201
    assert again.status_code == 409
    assert restored.status_code == 200
    assert restored.json()["name"] == "Running Shoes"
    assert restored.json()["version"] == 3


async def test_the_openapi_document_describes_the_import_endpoints(
    client: httpx.AsyncClient,
) -> None:
    spec = (await client.get("/openapi.json")).json()

    post = spec["paths"][IMPORTS]["post"]
    assert post["requestBody"]["content"]["multipart/form-data"]["schema"]["required"] == ["file"]
    assert {"202", "200", "401", "403", "413", "415", "422"} <= set(post["responses"])
    assert "409" in spec["paths"][f"{IMPORTS}/{{import_id}}/confirm"]["post"]["responses"]
    assert (
        "text/csv"
        in spec["paths"][f"{IMPORTS}/{{import_id}}/problems.csv"]["get"]["responses"]["200"][
            "content"
        ]
    )


async def test_revalidating_after_creating_the_category_replaces_the_report(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs, store: InMemoryStore
) -> None:
    data = csv_text(row(sku="G-1", category="Gardening"), row(sku="F-1")).encode()
    first = await uploaded_and_validated(client, admin, jobs, data)
    assert first["summary"]["unknown_categories"][0]["value"] == "Gardening"
    assert first["summary"]["error_rows"] == 1
    store.seed_categories(("Gardening", "gardening"))

    response = await client.post(f"{IMPORTS}/{first['id']}/revalidate", headers=admin)

    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "uploaded"
    assert queued["summary"] is None
    assert queued["problems"] == []
    assert queued["links"]["confirm"] is None
    page = (await client.get(f"{IMPORTS}/{first['id']}/problems", headers=admin)).json()
    assert page["items"] == []

    await jobs.validate(UUID(first["id"]))
    again = (await client.get(f"{IMPORTS}/{first['id']}", headers=admin)).json()

    assert again["status"] == "validated"
    assert again["summary"]["unknown_categories"] == []
    assert again["summary"]["error_rows"] == 0
    assert again["summary"]["importable_rows"] == 2
    assert again["problems"] == []
    assert again["links"]["confirm"] is not None


async def test_revalidating_twice_publishes_one_request(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs, store: InMemoryStore
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)

    first = await client.post(f"{IMPORTS}/{body['id']}/revalidate", headers=admin)
    second = await client.post(f"{IMPORTS}/{body['id']}/revalidate", headers=admin)

    assert first.status_code == second.status_code == 202
    requests = [
        item
        for item in store.import_data.outbox
        if item.event_type == "import.validation_requested"
    ]
    assert len(requests) == 2


async def test_revalidating_a_confirmed_import_is_a_409_and_keeps_it(
    client: httpx.AsyncClient, admin: dict[str, str], jobs: ImportJobs
) -> None:
    body = await uploaded_and_validated(client, admin, jobs)
    await client.post(f"{IMPORTS}/{body['id']}/confirm", headers=admin)

    response = await client.post(f"{IMPORTS}/{body['id']}/revalidate", headers=admin)

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Import cannot be validated again"
    assert response.json()["import_status"] == "queued"
    kept = (await client.get(f"{IMPORTS}/{body['id']}", headers=admin)).json()
    assert kept["status"] == "queued"
    assert kept["summary"]["importable_rows"] == 88


async def test_revalidating_an_unknown_import_is_a_404(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    assert (await client.post(f"{IMPORTS}/{uuid4()}/revalidate", headers=admin)).status_code == 404


async def test_revalidating_requires_an_admin(
    client: httpx.AsyncClient, admin: dict[str, str], customer: dict[str, str]
) -> None:
    created = (await upload(client, admin)).json()
    url = f"{IMPORTS}/{created['id']}/revalidate"

    assert (await client.post(url)).status_code == 401
    assert (await client.post(url, headers=customer)).status_code == 403
