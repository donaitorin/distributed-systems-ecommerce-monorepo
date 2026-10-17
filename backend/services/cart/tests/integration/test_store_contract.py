from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from cart_testing.support import SteppingClock, product
from redis.asyncio import Redis

from cart.application.ports import CartStore, ProductProjection
from cart.domain.cart import CartLine
from cart.infra.memory import InMemoryCartStore, InMemoryProductProjection
from cart.infra.redis_projection import PENDING_SECONDS, RedisProductProjection, product_key
from cart.infra.redis_store import RedisCartStore, cart_key, encode_line
from redis_support import PASSWORD, RedisServer

pytestmark = pytest.mark.integration

TTL = 1000
USER = "user-1"


@dataclass(slots=True)
class Kit:
    carts: CartStore
    projection: ProductProjection
    redis: Redis | None


@pytest.fixture(params=["memory", "redis"])
async def kit(request: pytest.FixtureRequest) -> AsyncIterator[Kit]:
    if request.param == "memory":
        yield Kit(InMemoryCartStore(), InMemoryProductProjection(), None)
        return
    server: RedisServer = request.getfixturevalue("redis_server")
    client = Redis(port=server.port, password=PASSWORD, decode_responses=True, socket_timeout=5)
    await client.flushall()
    yield Kit(RedisCartStore(client, TTL), RedisProductProjection(client, TTL), client)
    await client.aclose()


@pytest.fixture
async def redis_kit(redis_client: Redis) -> Kit:
    return Kit(
        RedisCartStore(redis_client, TTL), RedisProductProjection(redis_client, TTL), redis_client
    )


def line(sku: str = "RS-001", quantity: int = 1, clock: SteppingClock | None = None) -> CartLine:
    when = (clock or SteppingClock())()
    return CartLine.started(product(sku=sku), quantity, when)


async def test_a_line_is_stored_and_read_back_with_every_field(kit: Kit) -> None:
    stored = line(quantity=3)

    assert await kit.carts.put_line(USER, stored, 100) is True

    assert await kit.carts.get_line(USER, "RS-001") == stored
    assert await kit.carts.lines(USER) == [stored]


async def test_a_line_without_an_image_round_trips(kit: Kit) -> None:
    plain = CartLine.started(product(image_key=None, price="0.99"), 1, SteppingClock()())

    await kit.carts.put_line(USER, plain, 100)

    assert await kit.carts.get_line(USER, "RS-001") == plain


async def test_lines_come_back_in_the_order_they_were_added(kit: Kit) -> None:
    clock = SteppingClock()
    for sku in ("B-1", "A-1", "C-1"):
        await kit.carts.put_line(USER, line(sku, clock=clock), 100)

    assert [item.sku for item in await kit.carts.lines(USER)] == ["B-1", "A-1", "C-1"]


async def test_putting_a_line_again_replaces_it(kit: Kit) -> None:
    first = line(quantity=1)
    await kit.carts.put_line(USER, first, 100)

    await kit.carts.put_line(USER, first.with_quantity(7), 100)

    [only] = await kit.carts.lines(USER)
    assert only.quantity == 7


async def test_a_new_product_is_refused_when_the_cart_is_full_but_a_known_one_is_not(
    kit: Kit,
) -> None:
    await kit.carts.put_line(USER, line("A-1"), 2)
    await kit.carts.put_line(USER, line("B-1"), 2)

    refused = await kit.carts.put_line(USER, line("C-1"), 2)
    updated = await kit.carts.put_line(USER, line("A-1", quantity=5), 2)

    assert (refused, updated) == (False, True)
    assert sorted(item.sku for item in await kit.carts.lines(USER)) == ["A-1", "B-1"]


async def test_removing_a_line_leaves_the_others_and_is_idempotent(kit: Kit) -> None:
    await kit.carts.put_line(USER, line("A-1"), 100)
    await kit.carts.put_line(USER, line("B-1"), 100)

    await kit.carts.remove_line(USER, "A-1")
    await kit.carts.remove_line(USER, "A-1")
    await kit.carts.remove_line(USER, "NEVER-1")

    assert [item.sku for item in await kit.carts.lines(USER)] == ["B-1"]


async def test_removing_the_last_line_empties_the_cart(kit: Kit) -> None:
    await kit.carts.put_line(USER, line("A-1"), 100)

    await kit.carts.remove_line(USER, "A-1")

    assert await kit.carts.lines(USER) == []


async def test_clearing_removes_every_line_of_that_user_only(kit: Kit) -> None:
    await kit.carts.put_line(USER, line("A-1"), 100)
    await kit.carts.put_line("user-2", line("A-1"), 100)

    await kit.carts.clear(USER)

    assert await kit.carts.lines(USER) == []
    assert len(await kit.carts.lines("user-2")) == 1


async def test_an_unknown_cart_is_empty(kit: Kit) -> None:
    assert await kit.carts.lines("nobody") == []
    assert await kit.carts.get_line("nobody", "A-1") is None


async def test_applying_to_a_product_nobody_reserved_does_nothing(kit: Kit) -> None:
    applied = await kit.projection.apply_state(product(version=4))
    deleted = await kit.projection.apply_deletion("RS-001", 5)

    assert (applied, deleted) == (False, False)
    assert await kit.projection.read_many(["RS-001"]) == {}


async def test_a_reserved_product_takes_the_first_state(kit: Kit) -> None:
    await kit.projection.reserve("RS-001")

    applied = await kit.projection.apply_state(product(version=2, price="79.90"))

    assert applied is True
    assert await kit.projection.read_many(["RS-001"]) == {
        "RS-001": product(version=2, price="79.90")
    }


async def test_a_reservation_alone_is_not_a_product(kit: Kit) -> None:
    await kit.projection.reserve("RS-001")

    assert await kit.projection.read_many(["RS-001"]) == {}


async def test_reserving_twice_keeps_what_was_applied(kit: Kit) -> None:
    await kit.projection.reserve("RS-001")
    await kit.projection.apply_state(product(version=3))

    await kit.projection.reserve("RS-001")

    assert (await kit.projection.read_many(["RS-001"]))["RS-001"].version == 3


async def test_only_a_newer_version_is_applied(kit: Kit) -> None:
    await kit.projection.reserve("RS-001")
    await kit.projection.apply_state(product(version=3, price="30.00"))

    older = await kit.projection.apply_state(product(version=2, price="20.00"))
    same = await kit.projection.apply_state(product(version=3, price="99.00"))
    newer = await kit.projection.apply_state(product(version=4, price="40.00"))

    assert (older, same, newer) == (False, False, True)
    assert (await kit.projection.read_many(["RS-001"]))["RS-001"].price == Decimal("40.00")


async def test_events_applied_out_of_order_end_in_the_newest_state(kit: Kit) -> None:
    await kit.projection.reserve("RS-001")

    for version in (5, 2, 4, 1, 3):
        await kit.projection.apply_state(product(version=version, price=f"{version}.00"))

    state = (await kit.projection.read_many(["RS-001"]))["RS-001"]
    assert (state.version, state.price) == (5, Decimal("5.00"))


async def test_a_deletion_keeps_the_last_known_values_and_a_newer_update_restores(
    kit: Kit,
) -> None:
    await kit.projection.reserve("RS-001")
    await kit.projection.apply_state(product(version=2, price="30.00", stock=4))

    assert await kit.projection.apply_deletion("RS-001", 3) is True
    gone = (await kit.projection.read_many(["RS-001"]))["RS-001"]
    assert (gone.deleted, gone.version, gone.price, gone.stock) == (True, 3, Decimal("30.00"), 4)

    assert await kit.projection.apply_state(product(version=4, price="35.00")) is True
    back = (await kit.projection.read_many(["RS-001"]))["RS-001"]
    assert (back.deleted, back.price) == (False, Decimal("35.00"))


async def test_a_stale_deletion_does_not_hide_a_newer_product(kit: Kit) -> None:
    await kit.projection.reserve("RS-001")
    await kit.projection.apply_state(product(version=5))

    assert await kit.projection.apply_deletion("RS-001", 3) is False

    assert (await kit.projection.read_many(["RS-001"]))["RS-001"].deleted is False


async def test_a_deletion_that_arrives_while_the_product_is_only_reserved_is_remembered(
    kit: Kit,
) -> None:
    await kit.projection.reserve("RS-001")

    await kit.projection.apply_deletion("RS-001", 6)
    late = await kit.projection.apply_state(product(version=5))

    state = (await kit.projection.read_many(["RS-001"]))["RS-001"]
    assert (late, state.deleted, state.version) == (False, True, 6)


async def test_the_replay_of_the_same_events_changes_nothing(kit: Kit) -> None:
    await kit.projection.reserve("RS-001")
    events = [product(version=2, price="20.00"), product(version=3, price="30.00")]
    for event in events:
        await kit.projection.apply_state(event)
    before = await kit.projection.read_many(["RS-001"])

    results = [await kit.projection.apply_state(event) for event in events]

    assert results == [False, False]
    assert await kit.projection.read_many(["RS-001"]) == before


async def test_reading_many_returns_only_the_known_products(kit: Kit) -> None:
    for sku in ("A-1", "B-1"):
        await kit.projection.reserve(sku)
        await kit.projection.apply_state(product(sku=sku, version=2))
    await kit.projection.reserve("PENDING-1")

    states = await kit.projection.read_many(["A-1", "B-1", "PENDING-1", "MISSING-1"])

    assert sorted(states) == ["A-1", "B-1"]


async def test_the_cart_keeps_a_thirty_day_style_ttl_renewed_on_every_change(
    redis_kit: Kit,
) -> None:
    redis = redis_kit.redis
    assert redis is not None
    await redis_kit.carts.put_line(USER, line("A-1"), 100)
    await redis_kit.carts.put_line(USER, line("B-1"), 100)

    await redis.expire(cart_key(USER), 10)
    await redis_kit.carts.put_line(USER, line("A-1", quantity=2), 100)
    renewed_by_put = await redis.ttl(cart_key(USER))

    await redis.expire(cart_key(USER), 10)
    await redis_kit.carts.remove_line(USER, "B-1")
    renewed_by_remove = await redis.ttl(cart_key(USER))

    assert 0 < renewed_by_put <= TTL
    assert renewed_by_put > 10
    assert renewed_by_remove > 10


async def test_a_refused_put_does_not_renew_the_cart(redis_kit: Kit) -> None:
    redis = redis_kit.redis
    assert redis is not None
    await redis_kit.carts.put_line(USER, line("A-1"), 1)
    await redis.expire(cart_key(USER), 10)

    assert await redis_kit.carts.put_line(USER, line("B-1"), 1) is False

    assert await redis.ttl(cart_key(USER)) <= 10


async def test_a_reservation_is_short_lived_and_an_applied_state_lives_the_full_ttl(
    redis_kit: Kit,
) -> None:
    redis = redis_kit.redis
    assert redis is not None

    await redis_kit.projection.reserve("RS-001")
    pending = await redis.ttl(product_key("RS-001"))
    await redis_kit.projection.apply_state(product(version=2))
    applied = await redis.ttl(product_key("RS-001"))

    assert 0 < pending <= PENDING_SECONDS
    assert PENDING_SECONDS < applied <= TTL


async def test_reading_renews_the_projection_but_never_creates_it(redis_kit: Kit) -> None:
    redis = redis_kit.redis
    assert redis is not None
    await redis_kit.projection.reserve("RS-001")
    await redis_kit.projection.apply_state(product(version=2))
    await redis.expire(product_key("RS-001"), 10)

    await redis_kit.projection.read_many(["RS-001", "MISSING-1"])

    assert await redis.ttl(product_key("RS-001")) > 10
    assert await redis.exists(product_key("MISSING-1")) == 0


async def test_events_for_products_in_no_cart_never_create_keys(redis_kit: Kit) -> None:
    redis = redis_kit.redis
    assert redis is not None
    await redis_kit.projection.reserve("IN-CART-1")
    await redis_kit.projection.apply_state(product(sku="IN-CART-1", version=2))
    keys_before = await redis.dbsize()

    for number in range(2000):
        await redis_kit.projection.apply_state(
            product(sku=f"IMPORTED-{number}", version=1 + number % 3)
        )
        await redis_kit.projection.apply_deletion(f"IMPORTED-{number}", 9)

    assert await redis.dbsize() == keys_before == 1


async def test_a_line_added_before_the_cutoff_is_removed_and_the_others_stay(kit: Kit) -> None:
    clock = SteppingClock()
    first, second = line("A-1", clock=clock), line("B-2", clock=clock)
    await kit.carts.put_line(USER, first, 100)
    await kit.carts.put_line(USER, second, 100)

    removed = await kit.carts.remove_line_added_before(USER, "A-1", first.added_at)

    assert removed is True
    assert await kit.carts.lines(USER) == [second]


async def test_a_line_added_after_the_cutoff_is_kept(kit: Kit) -> None:
    clock = SteppingClock()
    older, newer = line("A-1", clock=clock), line("A-1", clock=clock)
    await kit.carts.put_line(USER, newer, 100)

    removed = await kit.carts.remove_line_added_before(USER, "A-1", older.added_at)

    assert removed is False
    assert await kit.carts.get_line(USER, "A-1") == newer


async def test_removing_a_line_that_is_not_there_does_nothing(kit: Kit) -> None:
    removed = await kit.carts.remove_line_added_before(USER, "A-1", SteppingClock()())

    assert removed is False
    assert await kit.carts.lines(USER) == []


async def test_the_redis_removal_loses_to_a_line_that_changed_in_between(
    redis_kit: Kit,
) -> None:
    assert redis_kit.redis is not None
    store = RedisCartStore(redis_kit.redis, TTL)
    stored = line("A-1")
    await store.put_line(USER, stored, 100)
    changed = stored.with_quantity(7)
    await store.put_line(USER, changed, 100)

    removed = await store._remove_if_unchanged(
        keys=[cart_key(USER)], args=["A-1", encode_line(stored)]
    )

    assert removed == 0
    assert await store.get_line(USER, "A-1") == changed
