import argparse
import json
import os
import sys
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ecommerce_auth.roles import Role
from ecommerce_auth.settings import DEFAULT_AUDIENCE
from ecommerce_auth.testing import STUB_ISSUER, StubTokenIssuer

DEV_KID = "dev-key"
DEV_SUBJECT = "00000000-0000-4000-8000-000000000001"
PRIVATE_KEY_FILE = "private.pem"
JWKS_FILE = "jwks.json"
JWKS_PATH = "/" + JWKS_FILE
HEALTH_PATH = "/health"
DEFAULT_PORT = 8080
DEFAULT_TTL_HOURS = 8.0


def ensure_keys(directory: Path) -> StubTokenIssuer:
    directory.mkdir(parents=True, exist_ok=True)
    private_path = directory / PRIVATE_KEY_FILE
    if private_path.exists():
        loaded = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        if not isinstance(loaded, rsa.RSAPrivateKey):
            raise ValueError(f"{private_path} does not hold an RSA private key")
        issuer = StubTokenIssuer(DEV_KID, loaded)
    else:
        issuer = StubTokenIssuer(DEV_KID)
        private_path.write_bytes(_to_pem(issuer))
        private_path.chmod(0o600)
    (directory / JWKS_FILE).write_text(json.dumps(issuer.jwks_document()))
    return issuer


def _to_pem(issuer: StubTokenIssuer) -> bytes:
    return issuer.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def build_jwks_server(jwks_document: bytes, host: str, port: int) -> ThreadingHTTPServer:
    class JwksHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == JWKS_PATH:
                self._respond(HTTPStatus.OK, jwks_document, "application/json")
            elif self.path == HEALTH_PATH:
                self._respond(HTTPStatus.OK, b'{"status":"ok"}', "application/json")
            else:
                self._respond(HTTPStatus.NOT_FOUND, b"{}", "application/json")

        def _respond(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return None

    return ThreadingHTTPServer((host, port), JwksHandler)


def run(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="ecommerce_auth.dev_tokens")
    parser.add_argument(
        "--keys-dir", type=Path, default=Path(os.environ.get("DEV_KEYS_DIR", "/keys"))
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)

    token = commands.add_parser("token")
    token.add_argument("--role", choices=[role.value for role in Role], default=Role.ADMIN.value)
    token.add_argument("--subject", default=DEV_SUBJECT)
    token.add_argument("--ttl-hours", type=float, default=DEFAULT_TTL_HOURS)

    args = parser.parse_args(argv)
    issuer = ensure_keys(args.keys_dir)

    if args.command == "serve":
        server = build_jwks_server(
            json.dumps(issuer.jwks_document()).encode(), args.host, args.port
        )
        server.serve_forever()
        return 0

    sys.stdout.write(
        issuer.issue(
            subject=args.subject,
            role=Role(args.role),
            audience=os.environ.get("JWT_AUDIENCE", DEFAULT_AUDIENCE),
            issuer=os.environ.get("JWT_ISSUER", STUB_ISSUER),
            expires_in_seconds=args.ttl_hours * 3600,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
