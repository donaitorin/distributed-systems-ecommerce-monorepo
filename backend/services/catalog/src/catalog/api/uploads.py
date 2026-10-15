from collections.abc import Mapping

from fastapi import Request
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import MultipartParser, parse_options_header

from catalog.application.errors import (
    InvalidUploadError,
    UnsupportedMediaError,
    UploadTooLargeError,
)
from catalog.domain.image import MAX_UPLOAD_BYTES, SIGNATURE_LENGTH, detect_image_format

FILE_FIELD = b"file"
MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES


class UploadCollector:
    def __init__(self) -> None:
        self._headers: dict[bytes, bytes] = {}
        self._header_name = b""
        self._header_value = b""
        self._file: bytearray | None = None
        self._receiving = False
        self._signature_checked = False
        self._file_parts = 0
        self.complete = False

    def callbacks(self) -> Mapping[str, object]:
        return {
            "on_part_begin": self._begin_part,
            "on_header_field": self._header_field,
            "on_header_value": self._header_value_chunk,
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._part_data,
            "on_part_end": self._end_part,
            "on_end": self._end_body,
        }

    def result(self) -> bytes:
        if self._file is None:
            raise InvalidUploadError("missing_file", "the multipart field 'file' is required")
        return bytes(self._file)

    def _begin_part(self) -> None:
        self._headers = {}
        self._receiving = False

    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def _header_value_chunk(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def _header_end(self) -> None:
        self._headers[self._header_name.lower()] = self._header_value
        self._header_name = b""
        self._header_value = b""

    def _headers_finished(self) -> None:
        _, options = parse_options_header(self._headers.get(b"content-disposition", b""))
        if options.get(b"name") != FILE_FIELD:
            return
        self._file_parts += 1
        if self._file_parts > 1:
            raise InvalidUploadError("multiple_files", "send exactly one 'file' part")
        self._file = bytearray()
        self._receiving = True

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        if not self._receiving or self._file is None:
            return
        if len(self._file) + (end - start) > MAX_UPLOAD_BYTES:
            raise UploadTooLargeError(MAX_UPLOAD_BYTES)
        self._file += data[start:end]
        if not self._signature_checked and len(self._file) >= SIGNATURE_LENGTH:
            self._signature_checked = True
            if detect_image_format(bytes(self._file[:SIGNATURE_LENGTH])) is None:
                raise UnsupportedMediaError("only JPEG, PNG and WebP images are accepted")

    def _end_part(self) -> None:
        self._receiving = False

    def _end_body(self) -> None:
        self.complete = True


def multipart_boundary(content_type: str | None) -> bytes:
    if content_type is None:
        raise UnsupportedMediaError("send the image as multipart/form-data")
    media_type, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if media_type != b"multipart/form-data" or not boundary:
        raise UnsupportedMediaError("send the image as multipart/form-data")
    return bytes(boundary)


def reject_oversized_declaration(content_length: str | None) -> None:
    if (
        content_length is not None
        and content_length.isdigit()
        and int(content_length) > MAX_REQUEST_BYTES
    ):
        raise UploadTooLargeError(MAX_UPLOAD_BYTES)


async def read_image_upload(request: Request) -> bytes:
    boundary = multipart_boundary(request.headers.get("content-type"))
    reject_oversized_declaration(request.headers.get("content-length"))
    collector = UploadCollector()
    parser = MultipartParser(boundary, collector.callbacks())  # type: ignore[arg-type]
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_REQUEST_BYTES:
                raise UploadTooLargeError(MAX_UPLOAD_BYTES)
            parser.write(chunk)
        parser.finalize()
    except FormParserError as error:
        raise InvalidUploadError(
            "malformed_multipart", "the multipart body is malformed"
        ) from error
    if not collector.complete:
        raise InvalidUploadError("malformed_multipart", "the multipart body is incomplete")
    return collector.result()
