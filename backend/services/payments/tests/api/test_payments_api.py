from uuid import uuid4

import httpx
import pytest
from payments_testing.data import CUSTOMER, OTHER_CUSTOMER, START, payment_requested
from payments_testing.support import bearer

from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer
from payments.domain.payment import NewPayment, PaymentStatus
from payments.infra.memory import InMemoryStore, InMemoryUnitOfWork

PAYMENTS = "/api/v1/payments"
EXPECTED_FIELDS = {
    "id",
    "order_id",
    "status",
    "amount",
    "currency",
    "card_last4",
    "failure_reason",
    "refunded_at",
    "created_at",
    "updated_at",
}


async def stored_payment(store: InMemoryStore, **overrides: object) -> str:
    envelope = payment_requested(**overrides)  # type: ignore[arg-type]
    payload = envelope.payload
    async with InMemoryUnitOfWork(store) as uow:
        await uow.payments.add(
            NewPayment(
                payload.order_id,
                payload.customer_id,
                payload.amount,
                payload.currency,
                payload.card_last4,
                envelope.correlation_id,
            ),
            START,
        )
        await uow.commit()
    return str(payload.order_id)


@pytest.fixture
def owner(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer, CUSTOMER)


async def test_the_owner_reads_the_payment_with_only_the_last_four_digits(
    client: httpx.AsyncClient, store: InMemoryStore, owner: dict[str, str]
) -> None:
    order_id = await stored_payment(store)

    response = await client.get(f"{PAYMENTS}/{order_id}", headers=owner)

    body = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert set(body) == EXPECTED_FIELDS
    assert (body["status"], body["amount"], body["currency"]) == (
        PaymentStatus.PENDING,
        "92.30",
        "USD",
    )
    assert body["card_last4"] == "1111"
    assert body["order_id"] == order_id
    assert "customer_id" not in body


async def test_an_admin_reads_any_payment(
    client: httpx.AsyncClient, store: InMemoryStore, issuer: StubTokenIssuer
) -> None:
    order_id = await stored_payment(store)

    response = await client.get(
        f"{PAYMENTS}/{order_id}", headers=bearer(issuer, uuid4(), Role.ADMIN)
    )

    assert response.status_code == 200


async def test_another_customer_gets_404_not_403(
    client: httpx.AsyncClient, store: InMemoryStore, issuer: StubTokenIssuer
) -> None:
    order_id = await stored_payment(store)

    response = await client.get(f"{PAYMENTS}/{order_id}", headers=bearer(issuer, OTHER_CUSTOMER))

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


async def test_an_order_without_a_payment_is_a_404(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    response = await client.get(f"{PAYMENTS}/{uuid4()}", headers=owner)

    assert response.status_code == 404
    assert response.json()["title"] == "Payment not found"


async def test_a_token_is_required(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{PAYMENTS}/{uuid4()}")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


async def test_a_malformed_order_id_is_a_422(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    assert (await client.get(f"{PAYMENTS}/nope", headers=owner)).status_code == 422


async def test_there_is_no_public_way_to_write_payments(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    for method in ("post", "put", "patch", "delete"):
        response = await getattr(client, method)(f"{PAYMENTS}/{uuid4()}", headers=owner)
        assert response.status_code == 405
    assert (await client.post(PAYMENTS, headers=owner, json={})).status_code in {404, 405}
