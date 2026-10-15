import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from testcontainers.core.container import DockerContainer

from ecommerce_storage import S3Settings, build_s3_client

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
S3_PORT = 8333
ACCESS_KEY = "test-access-key"
SECRET_KEY = "test-secret-key"
MEDIA_BUCKET = "media"
IMPORTS_BUCKET = "imports"
STARTUP_TIMEOUT_SECONDS = 90


@dataclass(frozen=True, slots=True)
class SeaweedFs:
    endpoint: str
    media_bucket: str = MEDIA_BUCKET
    imports_bucket: str = IMPORTS_BUCKET

    @property
    def settings(self) -> S3Settings:
        return S3Settings(ACCESS_KEY, SECRET_KEY, endpoint_url=self.endpoint)

    @property
    def public_base_url(self) -> str:
        return f"{self.endpoint}/{self.media_bucket}"


def pinned_seaweedfs_image() -> str:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    match = re.search(r"image:\s*(chrislusf/seaweedfs:\S+)", compose)
    assert match is not None, "docker-compose.yml no longer pins a SeaweedFS image"
    return match.group(1)


def wait_until_healthy(endpoint: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{endpoint}/healthz", timeout=2):
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(1)
    raise TimeoutError("SeaweedFS did not become healthy")


def create_buckets(server: SeaweedFs) -> None:
    client = build_s3_client(server.settings)
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    for bucket in (server.media_bucket, server.imports_bucket):
        while True:
            try:
                client.create_bucket(Bucket=bucket)
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)


@contextmanager
def run_seaweedfs() -> Iterator[SeaweedFs]:
    container = (
        DockerContainer(pinned_seaweedfs_image())
        .with_exposed_ports(S3_PORT)
        .with_env("OBJECT_STORAGE_ACCESS_KEY", ACCESS_KEY)
        .with_env("OBJECT_STORAGE_SECRET_KEY", SECRET_KEY)
        .with_env("OBJECT_STORAGE_MEDIA_BUCKET", MEDIA_BUCKET)
        .with_volume_mapping(
            str(REPOSITORY_ROOT / "infra" / "object-storage" / "start.sh"),
            "/scripts/start.sh",
            "ro",
        )
        .with_kwargs(entrypoint=["sh", "/scripts/start.sh"])
    )
    with container:
        host = container.get_container_host_ip()
        server = SeaweedFs(f"http://{host}:{container.get_exposed_port(S3_PORT)}")
        wait_until_healthy(server.endpoint)
        create_buckets(server)
        yield server
