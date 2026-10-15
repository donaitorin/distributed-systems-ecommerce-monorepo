from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt

from auth.application.ports import AccessToken
from auth.domain.user import Role
from auth.infra.keys import KeyStore

ALGORITHM = "RS256"


class JwtAccessTokenIssuer:
    def __init__(self, keys: KeyStore, issuer: str, audience: str, ttl: timedelta) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._ttl = ttl

    def issue(self, user_id: UUID, email: str, role: Role, now: datetime) -> AccessToken:
        claims = {
            "sub": str(user_id),
            "email": email,
            "role": role.value,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
            "jti": str(uuid4()),
        }
        active = self._keys.active
        token = jwt.encode(
            claims, active.private_key, algorithm=ALGORITHM, headers={"kid": active.kid}
        )
        return AccessToken(token, int(self._ttl.total_seconds()))
