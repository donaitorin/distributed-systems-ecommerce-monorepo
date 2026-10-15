# 0002. Catalog search: PostgreSQL full text with trigram fallback and keyset pagination

Status: accepted (2026-10-14)

## Context

`GET /api/v1/products` must support free text search that tolerates typos, filters, four sort orders and pagination that stays fast and stable with millions of rows. The spec fixes the technology (PostgreSQL full text search with GIN, `pg_trgm`, keyset cursors) and leaves the details open. The measurements below come from a 200,000 product synthetic catalog (`make seed`) on PostgreSQL 17.

## Decision

### Search

- `products.search_vector` is a `tsvector GENERATED ALWAYS AS (...) STORED` column: SKU and name with weight A, description with weight C. Names and descriptions use the `english` configuration (stemming: "running" matches "run"), SKUs use `simple`.
- Indexes, all partial on `deleted_at IS NULL`: GIN on `search_vector`, GIN `gin_trgm_ops` on `name`, btree on `(created_at, id)` and on `(price, id)`.
- `q` goes through `websearch_to_tsquery`, which never raises on user input.
- **Full text first, trigram only as a fallback.** A cheap existence probe asks whether full text matches anything within the other filters. If it does, the query uses full text only. If not, it uses `q <% name` (word similarity, threshold 0.5, set per transaction with `set_config(..., true)` so it is safe behind PgBouncer). The mode is decided once, on the first page of a walk, and then travels in the cursor (see below).
- Ranking: `ts_rank` with length and `rank/(rank+1)` normalization in full text mode, `word_similarity` in trigram mode. Ties break on `id`.

Why not a single `fts OR trigram` predicate? It is simpler and stateless, but the planner must be able to index both branches, and the trigram branch is unselective for common words. On 200,000 rows: full text alone takes 2 to 12 ms through the GIN index, while the OR took 400 to 650 ms with a sequential scan, even for correctly spelled queries.

### Cursors

The cursor is base64url JSON: `{v, d, s, h, m, k}` (format version, direction, effective sort, fingerprint of the filters, search mode, and the keyset position). The position is `(created_at, id)`, `(price, id)` or `(score, id)`, and `id` is always the tie-breaker in the same direction as the main key, so a row comparison walks the btree.

- **The search mode (`m`: `full_text`, `trigram` or null without `q`) is stored in the cursor and reused by every later page, `prev_cursor` included, and by the page's `total`.** Without it, a product created or deleted between two requests could flip the existence probe and switch the walk from one result set to another, repeating or skipping rows. With it, the matched set of a walk is fixed in kind; rows can still appear or disappear within it as data changes, but pages never change semantics. A request without a cursor probes again, so reloading the first page picks up the new situation. A forged cursor with a missing mode simply probes; a mode that is not one of the two values is rejected as `invalid_cursor`. Totals are computed in the stored mode, so a walk in trigram mode counts exact matches too.
- `prev_cursor` flips the comparison and the order, and the page is reversed after fetching `limit + 1` rows. The first page has no `prev_cursor` and the last has no `next_cursor`.
- The cursor is **validated but not signed**. Its values are only ever bound as query parameters, so tampering can produce an odd page but not injection. The version, field types, finiteness of scores and timezone awareness are checked.
- A cursor reused with a different `q`, `category`, price range, `in_stock` or sort answers `422` with `cursor_mismatch`; a malformed one answers `invalid_cursor`. `limit` is not part of the fingerprint.
- Signing the cursor with an HMAC is a possible hardening step. It needs a secret shared by all replicas and a rotation story, so it is left out until it is needed.
- Relevance scores round-trip exactly: they are computed as `double precision` and encoded with the shortest JSON representation that parses back to the same float. Tests walk result sets with many equal scores and cross page boundaries inside a tie group.

### Totals

`total` is cheap at any size. The planner's row estimate (`EXPLAIN (FORMAT JSON)`, planning only) is used when it is above 1000. When it is 1000 or below, a count capped at 1001 rows decides: at most 1000 means an exact total (`total_exact: true`), otherwise the response reports the estimate or the cap, whichever is larger, with `total_exact: false`. The seed script ends with `ANALYZE`.

The planner assumes independent terms, so a multi-word full text query whose words co-occur can be badly underestimated (on the synthetic data, "running shoes" was estimated below 1000 and really matches about 12,000 products). The value is then a lower bound.

### Time limit

Listing queries run with `SET LOCAL statement_timeout` (via `set_config(..., true)`, so it ends with the transaction and never leaks to pooled connections or other statements). The limit is `CATALOG_SEARCH_TIMEOUT_MS`, 2000 by default, between 1 and 60000. When PostgreSQL cancels a statement (SQLSTATE `57014`) the repository raises `SearchTimeoutError` and the API answers `503` Problem Details with `Retry-After: 1`. The handler logs a warning with the request id, path and limit; it deliberately does not log the query text.

### Migration and extension

`pg_trgm` is a trusted extension and `catalog_user` owns `catalog_db`, so migration 0003 runs `CREATE EXTENSION IF NOT EXISTS pg_trgm` without a superuser. A test runs the migration as a plain database owner. Putting it in the Postgres init script would not help existing volumes.

## Consequences and known limits

- **Relevance sort cost.** Keyset pagination on a computed score cannot use an index for ordering, so every relevance page scores the whole matched set. It is fine while a query matches thousands of rows and grows with the match count. The mitigation is the statement timeout above (a runaway query turns into a fast `503` instead of holding a connection), narrowing queries with filters, and moving relevance to OpenSearch behind the same API, as the spec already anticipates. The other three sorts walk a btree and cost the same on every page.
- **Typo fallback cost.** Trigram matching of a multi-word phrase is unselective: on 200,000 rows the fallback takes about 200 to 550 ms through a sequential scan, and a query with no match at all pays it too. Selective typo queries (rare words) use the trigram index. The statement timeout bounds the worst case.
- **The STORED generated column rewrites the table and holds an `ACCESS EXCLUSIVE` lock while it does.** That is acceptable for this project's size but not for a large live table. The zero-downtime alternative is: add a nullable `search_vector` column (a metadata-only change), create a trigger that fills it on insert and update, backfill existing rows in batches of a few thousand with short transactions, build the GIN index with `CREATE INDEX CONCURRENTLY`, then optionally swap to a generated column during a quiet window. The indexes in this migration are likewise built without `CONCURRENTLY`.
- English only. Other languages need their own configuration or `unaccent`.
- Totals can be wrong by a large factor in the correlated-terms case above; the UI should present them as approximate.
- `in_stock=false` and a blank `q` mean "no filter"; an unknown category slug yields an empty page, not an error.
