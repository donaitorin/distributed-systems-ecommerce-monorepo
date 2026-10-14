import httpx
import jwt
import pytest

from ecommerce_auth import JwksClient, KeysUnavailableError
from ecommerce_auth.testing import StubTokenIssuer, stub_settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class JwksServer:
    def __init__(self, issuers: list[StubTokenIssuer]) -> None:
        self.issuers = issuers
        self.calls = 0
        self.failing = False
        self.document_override: object | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.failing:
            return httpx.Response(503)
        if self.document_override is not None:
            return httpx.Response(200, json=self.document_override)
        keys = [key for issuer in self.issuers for key in issuer.jwks_document()["keys"]]
        return httpx.Response(200, json={"keys": keys})


def build_client(server: JwksServer, clock: FakeClock, **settings: float) -> JwksClient:
    transport = httpx.MockTransport(server.handle)
    return JwksClient(
        stub_settings(**settings), httpx.AsyncClient(transport=transport), clock=clock
    )


@pytest.fixture
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer("key-1")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


async def test_first_lookup_fetches_and_later_lookups_use_the_cache(
    issuer: StubTokenIssuer, clock: FakeClock
) -> None:
    server = JwksServer([issuer])
    client = build_client(server, clock)

    await client.get_key("key-1")
    await client.get_key("key-1")

    assert server.calls == 1


async def test_keys_are_refetched_after_the_ttl(issuer: StubTokenIssuer, clock: FakeClock) -> None:
    server = JwksServer([issuer])
    client = build_client(server, clock, keys_cache_ttl_seconds=300)
    await client.get_key("key-1")

    clock.advance(301)
    await client.get_key("key-1")

    assert server.calls == 2


async def test_unknown_kid_is_rejected_without_refetching_inside_the_cooldown(
    issuer: StubTokenIssuer, clock: FakeClock
) -> None:
    server = JwksServer([issuer])
    client = build_client(server, clock, keys_refetch_cooldown_seconds=30)
    await client.get_key("key-1")

    for _ in range(3):
        with pytest.raises(jwt.InvalidKeyError):
            await client.get_key("rotated-key")

    assert server.calls == 1


async def test_rotated_key_is_picked_up_after_the_cooldown(
    issuer: StubTokenIssuer, clock: FakeClock
) -> None:
    server = JwksServer([issuer])
    client = build_client(server, clock, keys_refetch_cooldown_seconds=30)
    await client.get_key("key-1")
    server.issuers.append(StubTokenIssuer("rotated-key"))

    clock.advance(31)
    key = await client.get_key("rotated-key")

    assert key is not None
    assert server.calls == 2


async def test_unavailable_endpoint_without_cached_keys_raises(clock: FakeClock) -> None:
    server = JwksServer([])
    server.failing = True
    client = build_client(server, clock)

    with pytest.raises(KeysUnavailableError):
        await client.get_key("key-1")


async def test_failed_fetch_is_not_retried_inside_the_cooldown(clock: FakeClock) -> None:
    server = JwksServer([])
    server.failing = True
    client = build_client(server, clock, keys_refetch_cooldown_seconds=30)

    for _ in range(3):
        with pytest.raises(KeysUnavailableError):
            await client.get_key("key-1")

    assert server.calls == 1


async def test_recovers_once_the_endpoint_comes_back(
    issuer: StubTokenIssuer, clock: FakeClock
) -> None:
    server = JwksServer([issuer])
    server.failing = True
    client = build_client(server, clock, keys_refetch_cooldown_seconds=30)
    with pytest.raises(KeysUnavailableError):
        await client.get_key("key-1")

    server.failing = False
    clock.advance(31)

    assert await client.get_key("key-1") is not None


async def test_stale_keys_keep_working_when_a_refresh_fails(
    issuer: StubTokenIssuer, clock: FakeClock
) -> None:
    server = JwksServer([issuer])
    client = build_client(server, clock, keys_cache_ttl_seconds=300)
    await client.get_key("key-1")
    server.failing = True

    clock.advance(301)

    assert await client.get_key("key-1") is not None


@pytest.mark.parametrize(
    "document",
    [
        {"unexpected": []},
        {"keys": "not-a-list"},
        {"keys": [{"kty": "RSA", "kid": "broken", "n": "x", "e": "y"}]},
        ["not", "an", "object"],
    ],
)
async def test_malformed_documents_count_as_unavailable(document: object, clock: FakeClock) -> None:
    server = JwksServer([])
    server.document_override = document
    client = build_client(server, clock)

    with pytest.raises(KeysUnavailableError):
        await client.get_key("key-1")


async def test_keys_that_are_not_rsa_or_have_no_kid_are_ignored(
    issuer: StubTokenIssuer, clock: FakeClock
) -> None:
    server = JwksServer([])
    server.document_override = {
        "keys": [
            {"kty": "oct", "kid": "symmetric", "k": "c2VjcmV0"},
            {k: v for k, v in issuer.jwks_document()["keys"][0].items() if k != "kid"},
            issuer.jwks_document()["keys"][0],
        ]
    }
    client = build_client(server, clock)

    assert await client.get_key("key-1") is not None
    with pytest.raises(jwt.InvalidKeyError):
        await client.get_key("symmetric")
