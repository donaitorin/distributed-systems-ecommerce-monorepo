import argparse
import asyncio
import base64
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, TextIO

from ecommerce_messaging.dead_letters import (
    DeadLetterEntry,
    Location,
    ReplayRefusedError,
    describe,
    parse_location,
    replay,
    require_dead_letter_topic,
)
from ecommerce_messaging.errors import ConsumeError, PublishError
from ecommerce_messaging.kafka import KafkaPublisher
from ecommerce_messaging.ports import IncomingMessage, Publisher
from ecommerce_messaging.settings import KafkaSettings
from ecommerce_messaging.topic_reader import KafkaTopicReader

CLIENT_ID = "dlq-cli"
EXIT_FAILURE = 1
EXIT_USAGE = 2


class TopicReader(Protocol):
    async def read_all(self, topic: str) -> list[IncomingMessage]: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dlq", description="Inspect and replay dead letters")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="list the messages of a dead letter topic")
    inspect.add_argument("topic")
    inspect.add_argument(
        "--show-payload",
        action="store_true",
        help="include the raw message value; it may contain personal data",
    )
    replay_command = commands.add_parser(
        "replay", help="publish dead letters again to their original topic"
    )
    replay_command.add_argument("topic")
    replay_command.add_argument(
        "--offset",
        action="append",
        default=[],
        metavar="PARTITION:OFFSET",
        help="a message to replay; repeat for several",
    )
    replay_command.add_argument("--all", action="store_true", help="replay every message")
    replay_command.add_argument(
        "--dry-run", action="store_true", help="show what would be replayed"
    )
    return parser


async def run(
    arguments: Sequence[str],
    reader: TopicReader,
    publisher: Publisher,
    out: TextIO,
    err: TextIO,
) -> int:
    parser = build_parser()
    try:
        options = parser.parse_args(arguments)
        topic = require_dead_letter_topic(options.topic)
        selected = _selection(options)
    except SystemExit as exit_request:
        return int(exit_request.code or EXIT_USAGE)
    except (ReplayRefusedError, ValueError) as error:
        err.write(f"error: {error}\n")
        return EXIT_USAGE
    entries = [describe(message) for message in await reader.read_all(topic)]
    if options.command == "inspect":
        for entry in entries:
            out.write(json.dumps(_row(entry, options.show_payload)) + "\n")
        return 0
    try:
        report = await replay(entries, publisher, selected, options.dry_run)
    except ReplayRefusedError as error:
        err.write(f"error: {error}\n")
        return EXIT_FAILURE
    verb = "would replay" if options.dry_run else "replayed"
    out.write(f"{verb} {len(report.replayed)} message(s) from {topic}\n")
    for partition, offset in report.missing:
        out.write(f"not found: {partition}:{offset}\n")
    return EXIT_FAILURE if report.missing else 0


def _selection(options: argparse.Namespace) -> set[Location] | None:
    if options.command != "replay":
        return None
    if bool(options.offset) == options.all:
        raise ReplayRefusedError("choose either --all or at least one --offset, not both")
    return {parse_location(raw) for raw in options.offset} if options.offset else None


def _row(entry: DeadLetterEntry, show_payload: bool) -> dict[str, Any]:
    row = entry.summary()
    if show_payload:
        row["payload_base64"] = base64.b64encode(entry.message.value).decode()
    return row


def main(
    environ: Mapping[str, str] | None = None,
    arguments: Sequence[str] | None = None,
    reader_for: Callable[[KafkaSettings], TopicReader] = KafkaTopicReader,
) -> int:
    values = os.environ if environ is None else environ
    settings = KafkaSettings.from_env(values, client_id=CLIENT_ID)
    publisher = KafkaPublisher(settings)

    async def execute() -> int:
        try:
            return await run(
                sys.argv[1:] if arguments is None else arguments,
                reader_for(settings),
                publisher,
                sys.stdout,
                sys.stderr,
            )
        except (ConsumeError, PublishError) as error:
            sys.stderr.write(f"error: {error}\n")
            return EXIT_FAILURE
        finally:
            await publisher.close()

    return asyncio.run(execute())


if __name__ == "__main__":
    raise SystemExit(main())
