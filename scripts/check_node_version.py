import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NVMRC = REPO_ROOT / "frontend" / ".nvmrc"
VERSION = re.compile(r"v?(\d+)(?:\.\d+)*")


def major_of(text: str) -> int | None:
    match = VERSION.fullmatch(text.strip())
    return int(match.group(1)) if match else None


def active_node_version() -> str | None:
    node = shutil.which("node")
    if node is None:
        return None
    result = subprocess.run([node, "--version"], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def check(wanted_text: str, active_text: str | None) -> str | None:
    wanted = major_of(wanted_text)
    if wanted is None:
        return f"frontend/.nvmrc does not hold a Node version: {wanted_text.strip()!r}"
    if active_text is None:
        return f"Node {wanted_text.strip()} is required (frontend/.nvmrc) but `node` was not found. Install it, for example with `nvm install` in frontend/."
    active = major_of(active_text)
    if active == wanted:
        return None
    return (
        f"Node {active_text.strip()} is active but frontend/.nvmrc asks for {wanted_text.strip()} "
        f"(major {wanted}). Run `cd frontend && nvm use` (or `nvm install`) and try again; "
        "the frontend toolchain and the pinned pnpm are built and tested on that major."
    )


def main(arguments: Sequence[str]) -> int:
    wanted = Path(arguments[0]) if arguments else NVMRC
    active = arguments[1] if len(arguments) > 1 else active_node_version()
    problem = check(wanted.read_text(), active)
    if problem is None:
        return 0
    sys.stderr.write(f"error: {problem}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
