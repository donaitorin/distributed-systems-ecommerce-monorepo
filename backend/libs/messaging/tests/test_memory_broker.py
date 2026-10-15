import pytest

from ecommerce_messaging import InMemoryBroker, OutgoingMessage, PublishError


def message(topic: str = "t", key: str = "k", value: bytes = b"v") -> OutgoingMessage:
    return OutgoingMessage(topic, key, value, {"h": b"1"})


async def test_published_messages_get_increasing_offsets_per_topic() -> None:
    broker = InMemoryBroker()

    await broker.publish(message("a"))
    await broker.publish(message("a"))
    await broker.publish(message("b"))

    assert [item.offset for item in broker.messages("a")] == [0, 1]
    assert [item.offset for item in broker.messages("b")] == [0]
    assert broker.messages("a")[0].headers == {"h": b"1"}
    assert broker.messages("a")[0].key == "k"


async def test_an_unavailable_broker_rejects_messages_and_stores_nothing() -> None:
    broker = InMemoryBroker()
    broker.available = False

    with pytest.raises(PublishError):
        await broker.publish(message())

    assert broker.messages("t") == []
    assert broker.published == []


async def test_a_source_reads_messages_in_order_and_then_nothing() -> None:
    broker = InMemoryBroker()
    await broker.publish(message(value=b"1"))
    await broker.publish(message(value=b"2"))
    source = broker.source(["t"])

    first, second, third = (
        await source.poll(0),
        await source.poll(0),
        await source.poll(0),
    )

    assert first is not None
    assert second is not None
    assert (first.value, second.value, third) == (b"1", b"2", None)


async def test_a_source_reads_several_topics() -> None:
    broker = InMemoryBroker()
    await broker.publish(message("a", value=b"A"))
    await broker.publish(message("b", value=b"B"))
    source = broker.source(["a", "b"])

    values = [(await source.poll(0)).value, (await source.poll(0)).value]  # type: ignore[union-attr]

    assert values == [b"A", b"B"]


async def test_uncommitted_messages_are_delivered_again_after_a_restart() -> None:
    broker = InMemoryBroker()
    await broker.publish(message(value=b"1"))
    await broker.publish(message(value=b"2"))
    source = broker.source(["t"])
    first = await source.poll(0)
    assert first is not None
    await source.commit(first)
    await source.poll(0)

    source.restart()

    again = await source.poll(0)
    assert again is not None
    assert again.value == b"2"
    assert source.commits == [first]


async def test_close_is_a_no_op() -> None:
    broker = InMemoryBroker()
    await broker.close()
    await broker.source(["t"]).close()
