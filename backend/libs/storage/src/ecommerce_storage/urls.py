from urllib.parse import quote, unquote

from ecommerce_storage.port import validate_key


def build_public_url(public_base_url: str, key: str) -> str:
    return f"{public_base_url.rstrip('/')}/{quote(validate_key(key))}"


def key_from_public_url(public_base_url: str, url: str) -> str | None:
    prefix = public_base_url.rstrip("/") + "/"
    if not url.startswith(prefix):
        return None
    key = unquote(url.removeprefix(prefix))
    try:
        return validate_key(key)
    except ValueError:
        return None
