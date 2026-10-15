import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from auth.infra.keys import generate_key_file, load_key_store
from auth.settings import DEFAULT_KEYS_DIR


def run(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="auth.tools.keys")
    parser.add_argument(
        "--keys-dir", type=Path, default=Path(os.environ.get("AUTH_KEYS_DIR", DEFAULT_KEYS_DIR))
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("generate")
    commands.add_parser("list")
    args = parser.parse_args(argv)

    if args.command == "generate":
        sys.stdout.write(generate_key_file(args.keys_dir).kid + "\n")
        return 0
    store = load_key_store(args.keys_dir, os.environ.get("AUTH_ACTIVE_KID") or None)
    for kid in store.kids:
        marker = " (active)" if kid == store.active.kid else ""
        sys.stdout.write(f"{kid}{marker}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
