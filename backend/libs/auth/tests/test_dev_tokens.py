import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ecommerce_auth import JwksClient, Role, TokenVerifier
from ecommerce_auth.dev_tokens import (
    DEV_KID,
    DEV_SUBJECT,
    JWKS_FILE,
    PRIVATE_KEY_FILE,
    build_jwks_server,
    ensure_keys,
    run,
)
from ecommerce_auth.testing import stub_settings


def test_first_run_generates_a_private_key_and_a_public_jwks(tmp_path: Path) -> None:
    ensure_keys(tmp_path)

    jwks = json.loads((tmp_path / JWKS_FILE).read_text())
    assert [key["kid"] for key in jwks["keys"]] == [DEV_KID]
    assert "d" not in jwks["keys"][0]
    assert (tmp_path / PRIVATE_KEY_FILE).stat().st_mode & 0o777 == 0o600


def test_later_runs_reuse_the_same_key(tmp_path: Path) -> None:
    first = ensure_keys(tmp_path)
    jwks_before = (tmp_path / JWKS_FILE).read_text()

    second = ensure_keys(tmp_path)

    assert first.jwks_document() == second.jwks_document()
    assert (tmp_path / JWKS_FILE).read_text() == jwks_before


def test_a_non_rsa_private_key_is_rejected(tmp_path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    (tmp_path / PRIVATE_KEY_FILE).write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    with pytest.raises(ValueError, match="RSA"):
        ensure_keys(tmp_path)


@pytest.fixture
def server(tmp_path: Path) -> Iterator[ThreadingHTTPServer]:
    issuer = ensure_keys(tmp_path)
    http_server = build_jwks_server(json.dumps(issuer.jwks_document()).encode(), "127.0.0.1", 0)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    yield http_server
    http_server.shutdown()
    http_server.server_close()


def url(server: ThreadingHTTPServer, path: str) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}{path}"


def test_server_serves_the_public_jwks(server: ThreadingHTTPServer) -> None:
    response = httpx.get(url(server, "/jwks.json"))

    assert response.status_code == 200
    assert response.json()["keys"][0]["kid"] == DEV_KID
    assert "d" not in response.json()["keys"][0]


def test_server_reports_health(server: ThreadingHTTPServer) -> None:
    assert httpx.get(url(server, "/health")).json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/private.pem", "/../private.pem", "/", "/keys/private.pem"])
def test_server_never_exposes_anything_else(server: ThreadingHTTPServer, path: str) -> None:
    response = httpx.get(url(server, path))

    assert response.status_code == 404
    assert "PRIVATE KEY" not in response.text


def test_token_command_prints_a_token_the_served_jwks_validates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(["--keys-dir", str(tmp_path), "token"]) == 0
    token = capsys.readouterr().out.strip()
    jwks = json.loads((tmp_path / JWKS_FILE).read_text())
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=jwks))
    settings = stub_settings()
    verifier = TokenVerifier(settings, JwksClient(settings, httpx.AsyncClient(transport=transport)))

    user = asyncio.run(verifier.verify(token))

    assert user.user_id == DEV_SUBJECT
    assert user.role is Role.ADMIN


def test_token_command_honours_role_subject_audience_and_issuer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_AUDIENCE", "custom-api")
    monkeypatch.setenv("JWT_ISSUER", "custom-issuer")

    run(["--keys-dir", str(tmp_path), "token", "--role", "customer", "--subject", "u-9"])

    claims = jwt.decode(capsys.readouterr().out.strip(), options={"verify_signature": False})
    assert claims["role"] == "customer"
    assert claims["sub"] == "u-9"
    assert claims["aud"] == "custom-api"
    assert claims["iss"] == "custom-issuer"


def test_unknown_role_is_rejected_by_the_cli(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        run(["--keys-dir", str(tmp_path), "token", "--role", "root"])


def test_serve_command_starts_the_server_with_the_generated_jwks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: dict[str, object] = {}

    class FakeServer:
        def serve_forever(self) -> None:
            started["serving"] = True

    def fake_build(document: bytes, host: str, port: int) -> FakeServer:
        started.update(document=json.loads(document), host=host, port=port)
        return FakeServer()

    monkeypatch.setattr("ecommerce_auth.dev_tokens.build_jwks_server", fake_build)

    assert run(["--keys-dir", str(tmp_path), "serve", "--port", "9999"]) == 0

    assert started["serving"] is True
    assert started["port"] == 9999
    assert started["document"] == json.loads((tmp_path / JWKS_FILE).read_text())
