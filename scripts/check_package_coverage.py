import re
import sys
import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

THRESHOLD = 85.0
CONDITION = re.compile(r"\((\d+)/(\d+)\)")
LIB_PREFIX = "ecommerce_"
SERVICE_DIRECTORIES = frozenset({"src", "migrations"})


@dataclass(slots=True)
class Totals:
    lines: int = 0
    lines_covered: int = 0
    branches: int = 0
    branches_covered: int = 0

    @property
    def percent(self) -> float:
        total = self.lines + self.branches
        return 100.0 if total == 0 else 100.0 * (self.lines_covered + self.branches_covered) / total


def package_of(filename: str) -> str | None:
    parts = filename.split("/")
    if len(parts) >= 3 and parts[1] == "src" and parts[2].startswith(LIB_PREFIX):
        return f"libs/{parts[0]}"
    if len(parts) >= 2 and parts[1] in SERVICE_DIRECTORIES:
        return f"services/{parts[0]}"
    return None


def totals_by_package(document: ElementTree.Element) -> dict[str, Totals]:
    result: dict[str, Totals] = {}
    for entry in document.iter("class"):
        package = package_of(entry.get("filename", ""))
        if package is None:
            continue
        totals = result.setdefault(package, Totals())
        for line in entry.iter("line"):
            totals.lines += 1
            totals.lines_covered += 1 if int(line.get("hits", "0")) > 0 else 0
            match = CONDITION.search(line.get("condition-coverage", ""))
            if match:
                totals.branches_covered += int(match.group(1))
                totals.branches += int(match.group(2))
    return result


def check(document: ElementTree.Element, threshold: float = THRESHOLD) -> tuple[list[str], list[str]]:
    report: list[str] = []
    failures: list[str] = []
    for package, totals in sorted(totals_by_package(document).items()):
        verdict = "ok  " if totals.percent >= threshold else "FAIL"
        report.append(f"{verdict} {package:<22} {totals.percent:6.2f}%")
        if totals.percent < threshold:
            failures.append(f"{package} is at {totals.percent:.2f}%, below {threshold:g}%")
    if not report:
        failures.append("no libs or services found in the coverage report")
    return report, failures


def main(arguments: Sequence[str]) -> int:
    path = Path(arguments[0] if arguments else "backend/coverage.xml")
    if not path.exists():
        sys.stderr.write(f"error: {path} not found; run the backend tests with coverage first\n")
        return 2
    report, failures = check(ElementTree.parse(path).getroot())
    sys.stdout.write("\n".join(report) + "\n")
    for failure in failures:
        sys.stderr.write(f"error: {failure}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
