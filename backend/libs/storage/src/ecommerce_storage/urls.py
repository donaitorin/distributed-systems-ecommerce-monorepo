from urllib.parse import quote

from ecommerce_storage.port import validate_key


def build_public_url(public_base_url: str, key: str) -> str:
    return f"{public_base_url.rstrip('/')}/{quote(validate_key(key))}"
