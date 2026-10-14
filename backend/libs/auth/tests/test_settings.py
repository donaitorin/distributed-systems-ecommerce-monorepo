import pytest

from ecommerce_auth import DEFAULT_AUDIENCE, JwtSettings


def test_from_env_uses_the_default_audience() -> None:
    settings = JwtSettings.from_env({"JWT_JWKS_URL": "http://auth/jwks", "JWT_ISSUER": "iss"})

    assert settings.jwks_url == "http://auth/jwks"
    assert settings.issuer == "iss"
    assert settings.audience == DEFAULT_AUDIENCE == "ecommerce-api"
    assert settings.keys_cache_ttl_seconds == 300.0


def test_from_env_reads_audience_and_cache_ttl() -> None:
    settings = JwtSettings.from_env(
        {
            "JWT_JWKS_URL": "http://auth/jwks",
            "JWT_ISSUER": "iss",
            "JWT_AUDIENCE": "other-api",
            "JWT_JWKS_CACHE_TTL_SECONDS": "60",
        }
    )

    assert settings.audience == "other-api"
    assert settings.keys_cache_ttl_seconds == 60.0


@pytest.mark.parametrize("missing", ["JWT_JWKS_URL", "JWT_ISSUER"])
def test_from_env_requires_jwks_url_and_issuer(missing: str) -> None:
    environ = {"JWT_JWKS_URL": "http://auth/jwks", "JWT_ISSUER": "iss"}
    del environ[missing]

    with pytest.raises(KeyError):
        JwtSettings.from_env(environ)
