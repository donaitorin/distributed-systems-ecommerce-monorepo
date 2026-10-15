# 0005. Auth: short-lived RS256 tokens, rotating refresh tokens and file-based signing keys

Status: accepted (2026-10-15)

## Context

The auth service owns credentials, roles and tokens. Every other service must validate an access token on its own, without calling auth, and the frontend (E8) will keep both tokens in `httpOnly` cookies and refresh them from its server side, where several page requests can race to refresh at the same time. This record covers how tokens are issued and rotated, where the signing key lives, and how passwords are stored.

## Decision

### Access tokens

- RS256 JWTs with `sub` (user id), `role`, `iss`, `aud`, `iat`, `exp` and `jti`, valid for 15 minutes. `libs/auth` verifies `iss`, `aud`, `sub`, `role` and `exp` against the JWKS.
- The `role` claim is read from the database whenever a token pair is issued, so a role change reaches the token on the next refresh, within 15 minutes. Access tokens cannot be revoked before they expire; logout and reuse detection act on refresh tokens only. 15 minutes is the accepted window.

### Refresh tokens

- Opaque, 256 random bits (`secrets.token_urlsafe(32)`). Only the SHA-256 of the token is stored: a fast hash is enough because the secret already has full entropy, and it makes the lookup by hash a single indexed query.
- Each login starts a **family**. Every rotation stays in the family and inherits its absolute expiry. A token lives 7 days, a family 30 days at most, so a session that keeps refreshing still ends with a new login.
- Rotation runs in one transaction that locks the token row (`SELECT ... FOR UPDATE`), marks it used and inserts the next token. Concurrent requests with the same token are serialized by the lock.
- **Reuse and the grace window.** Presenting a token that was already rotated:
  - within 10 seconds of its rotation: `401`, nothing else happens. This is the normal race between two page requests of the same session. The newest token is untouched, so the session continues.
  - after 10 seconds: the whole family is revoked and the answer is `401`. A token that old is not a race, it was copied.
- Revoked, expired, unknown and replayed tokens all produce the same `401` body, so a client cannot tell which one it hit. Reuse after the grace window is logged as a warning with the user and family ids.
- Trade-offs of the grace window: the loser of a race gets a `401` and has to retry with the winner's token (the frontend serializes refreshes per session for this reason), and an attacker who replays a stolen token within 10 seconds of the legitimate rotation is not detected by that request. A zero grace would make every race log the user out; the window is configurable (`AUTH_REFRESH_REUSE_GRACE_SECONDS`).
- `POST /logout` revokes the family of the presented token. It is idempotent and answers `204` even for unknown tokens.
- The service answers with JSON and sets no cookies; the frontend decides cookie attributes. Token responses carry `Cache-Control: no-store`.

### Signing keys

- Keys are PKCS8 PEM files in a directory (`AUTH_KEYS_DIR`, a Docker volume locally, a mounted secret elsewhere), never in the database or the repository. The `kid` is the RFC 7638 thumbprint of the public key, so it needs no naming convention.
- The JWKS lists the public part of **every** key in the directory. `AUTH_ACTIVE_KID` chooses the signing key; without it the most recently modified file signs.
- With `AUTH_GENERATE_KEY_IF_MISSING=true` (set in compose only) an empty directory gets a freshly generated 2048-bit key at startup. Otherwise an empty directory stops the service. Production should provide the key from a secret manager or KMS; this layout maps onto a mounted secret.
- **Rotation without downtime:**
  1. `python -m auth.tools.keys generate` adds a key. Deploy so the JWKS publishes both; verifiers fetch the JWKS again when they see an unknown `kid` (30 s cooldown, 5 min cache).
  2. Set `AUTH_ACTIVE_KID` to the new key and restart. New tokens are signed with it.
  3. After the access token lifetime plus the verifier cache (about 20 minutes), delete the old file.
- Keys are read once at startup, so a rotation is a deploy. Several auth replicas must share the same directory.

### Passwords and accounts

- Argon2id (`argon2-cffi`) with 19 MiB of memory, 2 iterations and 1 lane, the OWASP minimum, all configurable. The hash string carries its parameters, so a login with a hash made under older parameters stores a fresh one.
- Hashing runs in a thread, at most 4 at a time, so a login burst cannot exhaust memory or block the event loop.
- Policy (NIST 800-63B): 10 to 128 characters after NFKC normalization, no composition rules, no truncation or trimming, and a short list of very common passwords plus the email itself are rejected. The 128 limit bounds the hashing cost.
- Emails are trimmed, NFKC-normalized and lowercased, stored in that form with a unique constraint. The format check is structural (one `@`, a dotted domain, at most 254 characters); nothing verifies ownership of the address.
- Login answers the same `401` for an unknown email and a wrong password, and for an unknown email it still verifies the password against a decoy hash with the same parameters so the response time does not give the email away. Registration does answer `409` for a taken email; the gateway rate limit is the mitigation.
- The initial admin is created by `python -m auth.tools.seed` from `AUTH_ADMIN_EMAIL` and `AUTH_ADMIN_PASSWORD`, after the migration. It is idempotent: an existing account is never changed, so the seed cannot reset a password or role.

### Events, roles and rate limits

- `user.registered` (registration and the admin seed) and `user.role_changed` are written to the outbox table in the same transaction as the change, on topic `auth.events` keyed by user id (contracts in `libs/contracts`). A separate `auth-worker` container runs the relay, as `catalog-worker` does, so the API starts and answers `/ready` with only its database. The event carries the email because Accounts needs it for the backoffice list; it never carries a password or hash. The admin created before the outbox existed has no event; Accounts creates missing profiles on first use.
- `PATCH /users/{id}/role` is admin only. The auth service validates the token with the same `libs/auth` verifier as every other service, fed by its own key store instead of an HTTP fetch. An admin cannot change their own role (`409`), so the last admin cannot lock everyone out. Repeating the current role is a `200` without an event. The target user keeps working with the old role until the next refresh (at most 15 minutes), because the role is read when a token pair is issued.
- Traefik's `rateLimit` middleware limits `POST /login` (10 per minute, burst 10) and `POST /register` (5 per minute, burst 5) per source address. Limits: the counters live in the gateway process (not shared between gateway replicas), Docker Desktop makes every local client look like one address, the `429` is Traefik's plain-text body and not Problem Details, and nothing throttles a single account across many addresses.

## Consequences

- Services keep working while auth is down, until the cached JWKS and the tokens expire.
- A leaked refresh token is useful for at most 10 seconds after the legitimate client rotates it, and a replay later destroys the session, which is the intended signal.
- Expired and revoked refresh tokens are not purged yet; a retention job belongs with the other cleanup work.
- Account lockout per email is not implemented; throttling happens at the gateway, per address.
