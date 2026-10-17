from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from orders_testing.data import (
    ADDRESS,
    CARD_DIGITS,
    CARD_NUMBER,
    CUSTOMER,
    CUSTOMER_EMAIL,
    OTHER_CUSTOMER,
    SteppingClock,
    order_body,
)
from orders_testing.support import bearer

from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer
from orders.infra.memory import InMemoryStore

ORDERS = "/api/v1/orders"
ADMIN_ORDERS = "/api/v1/admin/orders"
KEY = {"Idempotency-Key": "checkout-0001"}


@pytest.fixture
def customer(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer, CUSTOMER)


@pytest.fixture
def other(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer, OTHER_CUSTOMER)


@pytest.fixture
def admin(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer, uuid4(), Role.ADMIN)


async def place(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
    key: str = "checkout-0001",
) -> httpx.Response:
    return await client.post(
        ORDERS, json=body or order_body(), headers=headers | {"Idempotency-Key": key}
    )


async def test_placing_an_order_answers_202_with_the_id_and_status(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await place(client, customer)

    body = response.json()
    assert response.status_code == 202
    assert body["status"] == "PENDING"
    assert response.headers["location"] == f"{ORDERS}/{body['id']}"
    assert response.headers["cache-control"] == "no-store"
    assert "idempotent-replay" not in response.headers
    UUID(body["id"])


async def test_the_same_key_and_body_return_the_same_response_and_say_it_is_a_replay(
    client: httpx.AsyncClient, customer: dict[str, str], store: InMemoryStore
) -> None:
    first = await place(client, customer)

    second = await place(client, customer)

    assert second.status_code == 202
    assert second.json() == first.json()
    assert second.headers["idempotent-replay"] == "true"
    assert second.headers["location"] == first.headers["location"]
    assert len(store.orders) == 1


async def test_the_same_body_written_differently_is_still_the_same_request(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    first = await place(client, customer)
    reordered = order_body(
        lines=[
            {"sku": "xs-001", "quantity": 1, "unit_price": "12.5"},
            {"sku": "RS-001", "quantity": 2, "unit_price": "39.9"},
        ],
        payment={"card_number": "4929-1234-5678-1111"},
    )

    second = await place(client, customer, reordered)

    assert second.json() == first.json()


async def test_the_same_key_with_a_different_body_is_rejected_with_a_clear_problem(
    client: httpx.AsyncClient, customer: dict[str, str], store: InMemoryStore
) -> None:
    await place(client, customer)
    different = one_line(sku="RS-001", quantity=9, unit_price="39.90")

    response = await place(client, customer, different)

    problem = response.json()
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert problem["code"] == "idempotency_key_reused"
    assert problem["title"] == "Idempotency key reused"
    assert "different request body" in problem["detail"]
    assert len(store.orders) == 1


async def test_another_customer_using_the_same_key_gets_their_own_order(
    client: httpx.AsyncClient, customer: dict[str, str], other: dict[str, str]
) -> None:
    mine = await place(client, customer)
    theirs = await place(client, other)

    assert theirs.status_code == 202
    assert theirs.json()["id"] != mine.json()["id"]


async def test_the_idempotency_key_is_required(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.post(ORDERS, json=order_body(), headers=customer)

    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_invalid"
    assert "required" in response.json()["detail"]


@pytest.mark.parametrize("key", ["short", "has spaces in it", "x" * 129])
async def test_a_malformed_idempotency_key_is_a_400(
    client: httpx.AsyncClient, customer: dict[str, str], key: str
) -> None:
    response = await place(client, customer, key=key)

    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_invalid"


async def test_placing_an_order_needs_a_token(client: httpx.AsyncClient) -> None:
    response = await client.post(ORDERS, json=order_body(), headers=KEY)

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


def one_line(**line: Any) -> dict[str, Any]:
    return order_body(lines=[{"sku": "A-1", "quantity": 1, "unit_price": "1.00"} | line])


def problem_locations(response: httpx.Response) -> set[str]:
    return {item["location"] for item in response.json()["errors"]}


@pytest.mark.parametrize(
    ("body", "location"),
    [
        (order_body(lines=[]), "body.lines"),
        (
            order_body(
                lines=[
                    {"sku": "A-1", "quantity": 1, "unit_price": "1.00"},
                    {"sku": "a-1", "quantity": 2, "unit_price": "1.00"},
                ]
            ),
            "body.lines",
        ),
        (
            one_line(sku="A-1", quantity=0, unit_price="1.00"),
            "body.lines.0.quantity",
        ),
        (
            one_line(sku="A-1", quantity=100, unit_price="1.00"),
            "body.lines.0.quantity",
        ),
        (
            one_line(sku="A-1", quantity=1, unit_price="-1.00"),
            "body.lines.0.unit_price",
        ),
        (
            one_line(sku="A-1", quantity=1, unit_price="1.005"),
            "body.lines.0.unit_price",
        ),
        (
            one_line(sku="no good", quantity=1, unit_price="1.00"),
            "body.lines.0.sku",
        ),
        (
            one_line(sku="A-1", quantity=99, unit_price="9999999999.99"),
            "body.lines",
        ),
        (
            order_body(shipping_address={**ADDRESS, "country": "Spain"}),
            "body.shipping_address.country",
        ),
        (order_body(shipping_address={**ADDRESS, "line1": ""}), "body.shipping_address.line1"),
        (order_body(payment={"card_number": "12345"}), "body.payment.card_number"),
        (order_body(payment={"card_number": "4929 abcd 5678 1111"}), "body.payment.card_number"),
        (order_body(payment={}), "body.payment.card_number"),
        (
            {k: v for k, v in order_body().items() if k != "shipping_address"},
            "body.shipping_address",
        ),
    ],
)
async def test_invalid_orders_are_a_422_with_the_field_location(
    client: httpx.AsyncClient,
    customer: dict[str, str],
    store: InMemoryStore,
    body: dict[str, Any],
    location: str,
) -> None:
    response = await place(client, customer, body)

    assert response.status_code == 422
    assert location in problem_locations(response)
    assert not store.orders


async def test_a_card_with_spaces_and_hyphens_is_accepted(
    client: httpx.AsyncClient, customer: dict[str, str], store: InMemoryStore
) -> None:
    response = await place(
        client, customer, order_body(payment={"card_number": "4929-1234-5678-1111"})
    )

    assert response.status_code == 202
    assert next(iter(store.orders.values())).card_last4 == "1111"


async def test_an_invalid_card_number_is_never_echoed_back(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await place(client, customer, order_body(payment={"card_number": "9999 888 7777x"}))

    assert response.status_code == 422
    assert "9999" not in response.text
    assert "7777" not in response.text


async def test_the_detail_of_a_new_order_has_lines_totals_and_history(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    created = (await place(client, customer)).json()

    response = await client.get(f"{ORDERS}/{created['id']}", headers=customer)

    body = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert (body["status"], body["total"], body["currency"]) == ("PENDING", "92.30", "USD")
    assert body["card_last4"] == "1111"
    assert body["customer_id"] == str(CUSTOMER)
    assert body["cancel_reason"] is None
    assert body["refunded_at"] is None
    assert body["shipping_address"]["city"] == "London"
    assert [(line["sku"], line["line_total"]) for line in body["lines"]] == [
        ("RS-001", "79.80"),
        ("XS-001", "12.50"),
    ]
    assert [(h["from_status"], h["to_status"]) for h in body["history"]] == [(None, "PENDING")]
    assert CARD_DIGITS not in response.text


async def test_an_order_is_visible_only_to_its_owner_and_other_customers_get_404(
    client: httpx.AsyncClient, customer: dict[str, str], other: dict[str, str]
) -> None:
    created = (await place(client, customer)).json()

    response = await client.get(f"{ORDERS}/{created['id']}", headers=other)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


async def test_an_unknown_or_malformed_order_id(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    unknown = await client.get(f"{ORDERS}/{uuid4()}", headers=customer)
    malformed = await client.get(f"{ORDERS}/not-a-uuid", headers=customer)

    assert unknown.status_code == 404
    assert malformed.status_code == 422


async def test_reading_orders_needs_a_token(client: httpx.AsyncClient) -> None:
    assert (await client.get(ORDERS)).status_code == 401
    assert (await client.get(f"{ORDERS}/{uuid4()}")).status_code == 401


async def test_the_list_shows_only_my_orders_newest_first_with_cursor_pagination(
    client: httpx.AsyncClient,
    customer: dict[str, str],
    other: dict[str, str],
    clock: SteppingClock,
) -> None:
    ids = []
    for index in range(30):
        clock.advance(seconds=1)
        ids.append((await place(client, customer, key=f"checkout-{index:04d}")).json()["id"])
    await place(client, other, key="their-key-0001")

    first = (await client.get(ORDERS, headers=customer)).json()
    second = (
        await client.get(ORDERS, params={"cursor": first["next_cursor"]}, headers=customer)
    ).json()

    assert [item["id"] for item in first["items"]] == list(reversed(ids))[:25]
    assert [item["id"] for item in second["items"]] == list(reversed(ids))[25:]
    assert second["next_cursor"] is None
    assert first["items"][0]["item_count"] == 3
    assert {item["customer_id"] for item in first["items"]} == {str(CUSTOMER)}


@pytest.mark.parametrize("limit", ["0", "10", "101", "abc"])
async def test_only_the_supported_page_sizes_are_accepted(
    client: httpx.AsyncClient, customer: dict[str, str], limit: str
) -> None:
    response = await client.get(ORDERS, params={"limit": limit}, headers=customer)

    assert response.status_code == 422


async def test_a_broken_cursor_is_a_422_on_the_cursor_parameter(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.get(ORDERS, params={"cursor": "garbage"}, headers=customer)

    assert response.status_code == 422
    assert problem_locations(response) == {"query.cursor"}


async def test_my_list_can_be_filtered_by_status(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    await place(client, customer)

    pending = (await client.get(ORDERS, params={"status": "PENDING"}, headers=customer)).json()
    cancelled = (await client.get(ORDERS, params={"status": "CANCELLED"}, headers=customer)).json()
    unknown = await client.get(ORDERS, params={"status": "SHIPPED"}, headers=customer)

    assert len(pending["items"]) == 1
    assert cancelled["items"] == []
    assert unknown.status_code == 422


async def test_admin_routes_reject_customers_and_anonymous_callers(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    order_id = (await place(client, customer)).json()["id"]

    assert (await client.get(ADMIN_ORDERS)).status_code == 401
    assert (await client.get(ADMIN_ORDERS, headers=customer)).status_code == 403
    assert (await client.get(f"{ADMIN_ORDERS}/{order_id}", headers=customer)).status_code == 403


async def test_an_admin_lists_every_order_and_reads_any_of_them(
    client: httpx.AsyncClient,
    customer: dict[str, str],
    other: dict[str, str],
    admin: dict[str, str],
) -> None:
    mine = (await place(client, customer)).json()["id"]
    theirs = (await place(client, other)).json()["id"]

    listing = (await client.get(ADMIN_ORDERS, headers=admin)).json()
    detail = await client.get(f"{ADMIN_ORDERS}/{theirs}", headers=admin)

    assert {item["id"] for item in listing["items"]} == {mine, theirs}
    assert detail.status_code == 200
    assert detail.json()["customer_id"] == str(OTHER_CUSTOMER)
    assert (await client.get(f"{ADMIN_ORDERS}/{uuid4()}", headers=admin)).status_code == 404


async def test_the_admin_list_filters_by_status_and_dates(
    client: httpx.AsyncClient,
    customer: dict[str, str],
    admin: dict[str, str],
    clock: SteppingClock,
) -> None:
    for index in range(3):
        clock.advance(seconds=60)
        await place(client, customer, key=f"checkout-{index:04d}")
    second_minute = "2026-10-17T12:02:00+00:00"
    third_minute = "2026-10-17T12:03:00+00:00"

    window = (
        await client.get(
            ADMIN_ORDERS,
            params={"created_from": second_minute, "created_to": third_minute},
            headers=admin,
        )
    ).json()
    pending = (await client.get(ADMIN_ORDERS, params={"status": "PENDING"}, headers=admin)).json()
    confirmed = (
        await client.get(ADMIN_ORDERS, params={"status": "CONFIRMED"}, headers=admin)
    ).json()

    assert len(window["items"]) == 1
    assert window["items"][0]["created_at"].startswith("2026-10-17T12:02:00")
    assert len(pending["items"]) == 3
    assert confirmed["items"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"created_from": "2026-10-17"},
        {"created_from": "2026-10-17T12:00:00"},
        {"created_from": "2026-10-18T00:00:00Z", "created_to": "2026-10-17T00:00:00Z"},
        {"created_from": "2026-10-17T00:00:00Z", "created_to": "2026-10-17T00:00:00Z"},
    ],
)
async def test_bad_date_filters_are_a_422(
    client: httpx.AsyncClient, admin: dict[str, str], params: dict[str, str]
) -> None:
    response = await client.get(ADMIN_ORDERS, params=params, headers=admin)

    assert response.status_code == 422
    assert problem_locations(response) & {"query.created_from", "query.created_to"}


async def test_the_card_number_is_not_in_anything_the_service_keeps(
    client: httpx.AsyncClient, customer: dict[str, str], store: InMemoryStore
) -> None:
    await place(client, customer)

    kept = repr(store.orders) + repr(store.idempotency) + repr(store.outbox)

    assert CARD_DIGITS not in kept
    assert CARD_NUMBER not in kept
    assert "4929" not in kept
    assert "1111" in kept


async def test_the_admin_sees_the_email_from_the_token_of_the_customer(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, admin: dict[str, str]
) -> None:
    signed_in = bearer(issuer, CUSTOMER, email=CUSTOMER_EMAIL)
    created = (await place(client, signed_in)).json()["id"]

    listing = (await client.get(ADMIN_ORDERS, headers=admin)).json()
    detail = (await client.get(f"{ADMIN_ORDERS}/{created}", headers=admin)).json()

    assert [item["customer_email"] for item in listing["items"]] == [CUSTOMER_EMAIL]
    assert detail["customer_email"] == CUSTOMER_EMAIL


async def test_a_token_without_an_email_leaves_it_null(
    client: httpx.AsyncClient, customer: dict[str, str], admin: dict[str, str]
) -> None:
    created = (await place(client, customer)).json()["id"]

    listing = (await client.get(ADMIN_ORDERS, headers=admin)).json()
    detail = (await client.get(f"{ADMIN_ORDERS}/{created}", headers=admin)).json()

    assert listing["items"][0]["customer_email"] is None
    assert detail["customer_email"] is None


@pytest.mark.parametrize("email", ["x" * 321 + "@example.com", "   "])
async def test_an_unusable_email_claim_is_ignored_instead_of_failing_the_order(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, admin: dict[str, str], email: str
) -> None:
    response = await place(client, bearer(issuer, CUSTOMER, email=email))

    detail = (await client.get(f"{ADMIN_ORDERS}/{response.json()['id']}", headers=admin)).json()
    assert response.status_code == 202
    assert detail["customer_email"] is None


async def test_the_email_is_not_part_of_what_a_customer_reads(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    signed_in = bearer(issuer, CUSTOMER, email=CUSTOMER_EMAIL)
    created = (await place(client, signed_in)).json()["id"]

    detail = await client.get(f"{ORDERS}/{created}", headers=signed_in)
    listing = await client.get(ORDERS, headers=signed_in)

    assert "customer_email" not in detail.json()
    assert "customer_email" not in listing.json()["items"][0]
    assert CUSTOMER_EMAIL not in detail.text + listing.text


async def test_a_replay_with_another_email_in_the_token_keeps_the_first_one(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, admin: dict[str, str]
) -> None:
    first = (await place(client, bearer(issuer, CUSTOMER, email=CUSTOMER_EMAIL))).json()["id"]

    again = await place(client, bearer(issuer, CUSTOMER, email="changed@example.com"))

    detail = (await client.get(f"{ADMIN_ORDERS}/{first}", headers=admin)).json()
    assert again.headers["idempotent-replay"] == "true"
    assert detail["customer_email"] == CUSTOMER_EMAIL
