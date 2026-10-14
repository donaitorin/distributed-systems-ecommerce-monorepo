import pytest
from botocore.stub import Stubber

from ecommerce_storage import (
    InvalidObjectKeyError,
    ObjectStorage,
    S3ObjectStorage,
    S3Settings,
    build_s3_client,
)

BUCKET = "media"
BASE_URL = "http://localhost:8000/media"


def seaweed_settings() -> S3Settings:
    return S3Settings(
        access_key="access",
        secret_key="secret",
        endpoint_url="http://object-storage:8333",
    )


def test_settings_from_env_reads_the_endpoint_and_defaults_the_region() -> None:
    settings = S3Settings.from_env(
        {
            "OBJECT_STORAGE_ACCESS_KEY": "a",
            "OBJECT_STORAGE_SECRET_KEY": "s",
            "OBJECT_STORAGE_ENDPOINT": "http://object-storage:8333",
        }
    )

    assert settings == S3Settings("a", "s", "us-east-1", "http://object-storage:8333")


def test_settings_from_env_treats_an_empty_endpoint_as_aws() -> None:
    settings = S3Settings.from_env(
        {
            "OBJECT_STORAGE_ACCESS_KEY": "a",
            "OBJECT_STORAGE_SECRET_KEY": "s",
            "OBJECT_STORAGE_REGION": "eu-west-1",
            "OBJECT_STORAGE_ENDPOINT": "",
        }
    )

    assert settings.endpoint_url is None
    assert settings.region == "eu-west-1"


def test_settings_from_env_requires_credentials() -> None:
    with pytest.raises(KeyError):
        S3Settings.from_env({"OBJECT_STORAGE_ACCESS_KEY": "a"})


def test_custom_endpoint_uses_path_style_addressing() -> None:
    client = build_s3_client(seaweed_settings())

    assert client.meta.endpoint_url == "http://object-storage:8333"
    assert vars(client.meta.config)["s3"] == {"addressing_style": "path"}


def test_without_endpoint_the_client_targets_aws_with_default_addressing() -> None:
    client = build_s3_client(S3Settings(access_key="a", secret_key="s", region="eu-west-1"))

    assert client.meta.endpoint_url == "https://s3.eu-west-1.amazonaws.com"
    assert vars(client.meta.config)["s3"] == {"addressing_style": "auto"}


def test_s3_adapter_satisfies_the_port() -> None:
    storage: ObjectStorage = S3ObjectStorage(build_s3_client(seaweed_settings()), BUCKET, BASE_URL)

    assert storage.public_url("products/a.webp") == f"{BASE_URL}/products/a.webp"


async def test_put_uploads_with_bucket_key_and_content_type() -> None:
    client = build_s3_client(seaweed_settings())
    storage = S3ObjectStorage(client, BUCKET, BASE_URL)

    with Stubber(client) as stubber:
        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": BUCKET,
                "Key": "products/a.webp",
                "Body": b"image",
                "ContentType": "image/webp",
            },
        )
        await storage.put("products/a.webp", b"image", "image/webp")
        stubber.assert_no_pending_responses()


async def test_delete_removes_the_key_from_the_bucket() -> None:
    client = build_s3_client(seaweed_settings())
    storage = S3ObjectStorage(client, BUCKET, BASE_URL)

    with Stubber(client) as stubber:
        stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": "products/a.webp"})
        await storage.delete("products/a.webp")
        stubber.assert_no_pending_responses()


@pytest.mark.parametrize("key", ["", "/abs", "../escape"])
async def test_invalid_keys_never_reach_s3(key: str) -> None:
    client = build_s3_client(seaweed_settings())
    storage = S3ObjectStorage(client, BUCKET, BASE_URL)

    with Stubber(client) as stubber:
        with pytest.raises(InvalidObjectKeyError):
            await storage.put(key, b"x", "text/plain")
        with pytest.raises(InvalidObjectKeyError):
            await storage.delete(key)
        stubber.assert_no_pending_responses()
