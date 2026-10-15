from collections.abc import MutableMapping
from typing import Any

import pytest
from catalog_testing import images
from starlette.requests import Request

from catalog.api.uploads import (
    MAX_REQUEST_BYTES,
    multipart_boundary,
    read_image_upload,
    reject_oversized_declaration,
)
from catalog.application.errors import (
    InvalidUploadError,
    UnsupportedMediaError,
    UploadTooLargeError,
)
from catalog.domain.image import MAX_UPLOAD_BYTES

CHUNK = 64 * 1024
HEADER = b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\n\r\n'


class ScriptedBody:
    def __init__(self, chunks: list[bytes], endless: bytes | None = None) -> None:
        self._chunks = chunks
        self._endless = endless
        self.delivered = 0
        self.consumed_bytes = 0

    async def receive(self) -> MutableMapping[str, Any]:
        if self._chunks:
            chunk, more = self._chunks.pop(0), bool(self._chunks) or self._endless is not None
        elif self._endless is not None:
            chunk, more = self._endless, True
        else:
            chunk, more = b"", False
        self.delivered += 1
        self.consumed_bytes += len(chunk)
        return {"type": "http.request", "body": chunk, "more_body": more}


def request_for(
    body: ScriptedBody, content_type: str, content_length: str | None = None
) -> Request:
    headers = [(b"content-type", content_type.encode())]
    if content_length is not None:
        headers.append((b"content-length", content_length.encode()))
    scope = {"type": "http", "method": "PUT", "path": "/", "headers": headers}
    return Request(scope, body.receive)


async def test_a_well_formed_upload_is_returned_whole() -> None:
    data = images.jpeg()
    payload, content_type = images.multipart([("file", "a.jpg", data, "image/jpeg")])
    chunks = [payload[index : index + 1000] for index in range(0, len(payload), 1000)]

    result = await read_image_upload(request_for(ScriptedBody(chunks), content_type))

    assert result == data


async def test_an_endless_body_is_abandoned_soon_after_the_limit() -> None:
    body = ScriptedBody([HEADER], endless=b"\xff\xd8\xff\xe0" + b"0" * (CHUNK - 4))

    with pytest.raises(UploadTooLargeError):
        await read_image_upload(request_for(body, "multipart/form-data; boundary=b"))

    assert body.consumed_bytes <= MAX_REQUEST_BYTES + 2 * CHUNK


async def test_a_non_image_is_abandoned_after_the_first_bytes() -> None:
    body = ScriptedBody([HEADER + b"plain text, definitely not an image"], endless=b"x" * CHUNK)

    with pytest.raises(UnsupportedMediaError):
        await read_image_upload(request_for(body, "multipart/form-data; boundary=b"))

    assert body.delivered <= 2


async def test_a_declared_length_over_the_limit_reads_nothing() -> None:
    body = ScriptedBody([], endless=b"x" * CHUNK)

    with pytest.raises(UploadTooLargeError):
        await read_image_upload(
            request_for(
                body, "multipart/form-data; boundary=b", content_length=str(MAX_REQUEST_BYTES + 1)
            )
        )

    assert body.delivered == 0


async def test_a_body_without_the_closing_boundary_is_malformed() -> None:
    body = ScriptedBody([HEADER + images.jpeg()])

    with pytest.raises(InvalidUploadError) as raised:
        await read_image_upload(request_for(body, "multipart/form-data; boundary=b"))

    assert raised.value.code == "malformed_multipart"


@pytest.mark.parametrize("length", [None, "abc", "", str(MAX_REQUEST_BYTES)])
def test_acceptable_or_unusable_declared_lengths_are_not_rejected_up_front(
    length: str | None,
) -> None:
    reject_oversized_declaration(length)


def test_the_boundary_is_read_from_the_content_type() -> None:
    assert multipart_boundary('multipart/form-data; boundary="abc123"') == b"abc123"


@pytest.mark.parametrize(
    "content_type",
    [None, "", "application/json", "multipart/form-data", "multipart/mixed; boundary=x"],
)
def test_anything_but_form_data_with_a_boundary_is_unsupported(content_type: str | None) -> None:
    with pytest.raises(UnsupportedMediaError):
        multipart_boundary(content_type)


def test_the_request_budget_leaves_room_for_the_multipart_framing() -> None:
    assert MAX_REQUEST_BYTES > MAX_UPLOAD_BYTES
