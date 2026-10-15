# 0006. Accounts: an eventually consistent profile ordered by timestamps

Status: accepted (2026-10-15)

## Context

Auth owns identity and roles; accounts owns the profile and the backoffice user list, and keeps its own copy of the email and the role. The copy is fed from two independent paths: the `user.registered` and `user.role_changed` events on `auth.events`, and a lazy insert from the token claims on the first authenticated `/me` request. The seeded admin has no registration event and a new user can call accounts before their event is consumed, so the two paths race. Kafka only orders events for the same key; it says nothing about the lazy path.

## Decision

- **The copy never grants anything.** Authorization uses the role in the verified token. The local role is for display and filtering, so a stale value is a cosmetic problem, not a security one.
- **Last write wins by timestamp, per profile.** The role is stored with `role_updated_at`. A write changes the role only if its timestamp is strictly newer. Timestamps come from the same source, the auth service: `registered_at`, `changed_at`, and the token `iat` (the token role is read from auth's database when the pair is issued). An equal timestamp changes nothing.
- **The rule lives in the repository and is atomic.** Each write is one `INSERT ... ON CONFLICT DO UPDATE ... WHERE` statement, so concurrent handlers and requests converge without locks or retries. Order of arrival does not matter: every interleaving of the same writes ends in the same row, which the Postgres tests check by racing the three writers on twenty users.
- **No role time means any event wins.** A token without `iat` stores `role_updated_at` as `NULL`. Using the insert time instead could make a real role change that happened between issue and insert look older and be dropped. The first event stamps the time and the strict rule applies from then on.
- **Different writers own different fields.** Events own `email` and `role`; the user owns `name`, `phone` and addresses. `user.registered` fills an empty email but never replaces one, and never touches the user's fields. The lazy path only inserts.
- **Idempotency is a claim in the same transaction.** `processed_events(consumer_group, event_id)` is written in the transaction of the handler (`transactional_handler`), so a crash between the effect and the claim cannot happen, and a republished event with the same id is a no-op. Invalid or unsupported messages go to `auth.events.dlq`; there is no business state to mark.
- **A role change before the registration creates the profile** with the role and no email instead of failing; the registration completes it later.

## Consequences

- A new profile can exist for a few seconds without being "complete" (no event yet): the email may be empty if the token predates the `email` claim. Callers must treat `email` as nullable.
- Token `iat` has one-second resolution while event times have microseconds. In the worst case a role change in the same second as a token being issued is applied after the lazy insert and is transiently visible; events for one user are ordered by Kafka, so the final role is still the last one.
- Timestamps rely on one clock (auth's). If events ever came from several producers, a version number per user would be needed; adding an optional field to the events is backward compatible.
- `processed_events` grows without bound (shared limitation of the messaging library; retention is pending).
- Logs carry the event id, correlation id and user id, never the email.
