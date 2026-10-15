import codecs
import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Final

from catalog.domain.csv_import import problems as codes
from catalog.domain.csv_import.problems import Problem, error

REQUIRED_COLUMNS: Final = ("name", "sku", "price", "stock")
OPTIONAL_COLUMNS: Final = ("description", "category", "weight_kg")
KNOWN_COLUMNS: Final = frozenset((*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS))
BYTE_ORDER_MARK: Final = "﻿"
UTF16_MARKS: Final = (b"\xff\xfe", b"\xfe\xff")
ALTERNATIVE_SEPARATORS: Final = {";": "semicolon", "\t": "tab", "|": "pipe"}


@dataclass(frozen=True, slots=True)
class Header:
    columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RawRecord:
    row: int
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Rejection:
    problems: tuple[Problem, ...]


type DocumentEvent = Header | RawRecord | Rejection


def read_document(chunks: Iterable[bytes]) -> Iterator[DocumentEvent]:
    reader = csv.reader(_lines(chunks), strict=True)
    row = 0
    header: Header | None = None
    data_rows = 0
    try:
        for fields in reader:
            row += 1
            blank = not any(field.strip() for field in fields)
            if header is None:
                if blank:
                    continue
                outcome = check_header(fields, row)
                if isinstance(outcome, Rejection):
                    yield outcome
                    return
                header = outcome
                yield header
                continue
            if not blank:
                data_rows += 1
            yield RawRecord(row, tuple(fields))
    except UndecodableError as failure:
        yield Rejection((failure.problem,))
        return
    except csv.Error as failure:
        reason = f"not a valid CSV: {failure}"
        yield Rejection((error(row + 1, None, None, codes.MALFORMED_CSV, reason),))
        return
    if header is None:
        yield Rejection((error(None, None, None, codes.EMPTY_FILE, "the file is empty"),))
    elif data_rows == 0:
        reason = "the file has a header but no data rows"
        yield Rejection((error(None, None, None, codes.NO_ROWS, reason),))


def check_header(fields: list[str], row: int) -> Header | Rejection:
    columns = tuple(" ".join(field.split()).casefold() for field in fields)
    problems: list[Problem] = []
    seen: set[str] = set()
    for original, column in zip(fields, columns, strict=True):
        if column in seen:
            reason = f"column {column} appears more than once"
            problems.append(error(row, original, original, codes.DUPLICATE_COLUMN, reason))
        elif column not in KNOWN_COLUMNS:
            reason = unknown_column_reason(original, fields)
            problems.append(error(row, original, original, codes.UNKNOWN_COLUMN, reason))
        seen.add(column)
    problems.extend(
        error(row, column, None, codes.MISSING_COLUMN, f"required column {column} is missing")
        for column in REQUIRED_COLUMNS
        if column not in seen
    )
    return Rejection(tuple(problems)) if problems else Header(columns)


def unknown_column_reason(original: str, fields: list[str]) -> str:
    if len(fields) == 1:
        for separator, name in ALTERNATIVE_SEPARATORS.items():
            if separator in original:
                return f"the columns look {name}-separated; use commas"
    allowed = ", ".join((*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS))
    return f"unknown column; allowed columns are {allowed}"


class UndecodableError(Exception):
    def __init__(self, problem: Problem) -> None:
        super().__init__(problem.reason)
        self.problem = problem


def _decoded(chunks: Iterable[bytes]) -> Iterator[str]:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    first_bytes = b""
    started = False
    offset = 0
    try:
        for chunk in chunks:
            if b"\x00" in chunk:
                raise UndecodableError(
                    error(None, None, None, codes.NOT_TEXT, "the file is binary, not CSV text")
                )
            first_bytes = (first_bytes + chunk)[: len(UTF16_MARKS[0])]
            text = decoder.decode(chunk)
            offset += len(chunk)
            if not started and text:
                started = True
                text = text.removeprefix(BYTE_ORDER_MARK)
            if text:
                yield text
        decoder.decode(b"", final=True)
    except UnicodeDecodeError as failure:
        raise UndecodableError(
            error(
                None,
                None,
                None,
                codes.INVALID_ENCODING,
                _encoding_reason(first_bytes, offset + failure.start),
            )
        ) from failure


def _encoding_reason(first_bytes: bytes, position: int) -> str:
    if first_bytes in UTF16_MARKS:
        return "the file looks UTF-16 encoded; save it as UTF-8"
    return f"the file is not valid UTF-8 (invalid byte near position {position})"


def _lines(chunks: Iterable[bytes]) -> Iterator[str]:
    buffer = ""
    for text in _decoded(chunks):
        buffer += text
        start = 0
        while (index := buffer.find("\n", start)) != -1:
            yield buffer[start : index + 1]
            start = index + 1
        buffer = buffer[start:]
    if buffer:
        yield buffer
