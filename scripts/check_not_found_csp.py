import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from html.parser import HTMLParser

NONCE = re.compile(r"'nonce-([^']+)'")
RANDOM_SEGMENT = "this-page-does-not-exist"


class InlineFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inline: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "style" or (tag == "script" and "src" not in values):
            self.inline.append((tag, values.get("nonce")))


def violations(html: str, policy: str | None) -> list[str]:
    if policy is None:
        return ["the response has no Content-Security-Policy header"]
    match = NONCE.search(policy)
    if match is None:
        return ["the Content-Security-Policy has no nonce"]
    finder = InlineFinder()
    finder.feed(html)
    return [
        f"<{tag}> without the policy nonce"
        for tag, nonce in finder.inline
        if nonce != match.group(1)
    ]


def fetch(url: str) -> tuple[int, str, str | None]:
    try:
        response = urllib.request.urlopen(url, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read().decode(errors="replace")
        return response.status, body, response.headers.get("Content-Security-Policy")


def main(arguments: Sequence[str]) -> int:
    port = os.environ.get("GATEWAY_HTTP_PORT", "8000")
    gateway = arguments[0] if arguments else f"http://127.0.0.1:{port}"
    failed = False
    for name, path in (("store", f"/{RANDOM_SEGMENT}"),):
        status, html, policy = fetch(gateway + path)
        problems = [] if status == 404 else [f"expected 404, got {status}"]
        problems += violations(html, policy)
        for problem in problems:
            sys.stderr.write(f"FAIL {name} {path}: {problem}\n")
        failed = failed or bool(problems)
        if not problems:
            sys.stdout.write(f"ok   {name} not-found page renders under the nonce policy\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
