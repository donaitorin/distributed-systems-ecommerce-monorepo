# 0004. CSV import: asynchronous validation, explicit confirmation and a reusable messaging core

Status: accepted (2026-10-15)

## Context

Admins load products from CSV files that can be large and are full of mistakes. The spec requires that the whole file is validated before anything is written, that every problem is reported, that nothing is imported without an explicit confirmation, and that uploading the same file twice does not duplicate work. This is also the first service-to-service use of Kafka, so the messaging building blocks are written once, generically, for the auth and accounts services (E6, E7) to reuse.

## Decision

### Flow and states

```text
uploaded ─► validating ─► validated ──confirm──► queued ─► processing ─► completed
                │                                                  │
                ├─► rejected   (the whole file is unusable)        └─► failed
                └─► failed     (a worker error survived its retries)
```

- `POST /api/v1/imports` streams the file to the private `imports` bucket (multipart upload with abort on failure, so memory stays at one part), hashing it and enforcing `IMPORT_MAX_BYTES` (50 MB by default) while reading. In one transaction it inserts the `imports` row and an outbox row for `import.validation_requested`. It answers `202`.
- The hash is unique for every import that has not failed. Uploading the same bytes again returns the existing import with `200` and deletes the duplicate object. A failed import can be uploaded again.
- **Validation runs in the worker, not in the request.** Parsing, checking categories and classifying every row against the database takes seconds to minutes for realistic files, and a background task inside the API process would be lost if it died. The worker reads the object in a thread, runs the pure pipeline (`catalog.domain.csv_import`) twice (report, then a pass over the winning rows to count creates, updates, restores and unchanged rows) and stores the report, the capped list of problems and a snapshot of the categories.
- `POST /api/v1/imports/{id}/confirm` is the only way to write anything. It works from `validated` with at least one valid row (`409` otherwise), writes `queued` and the `import.requested` outbox row in one transaction and answers `202`. Repeating it is harmless.
- The worker re-reads the file with the stored category snapshot, so it imports exactly what was previewed, then upserts in batches of 1000 and records progress per batch.
- Everything is admin only; errors are Problem Details.

### The report

`GET /api/v1/imports/{id}` returns the status, counts, the unknown categories grouped with a suggestion, the first 100 problems (errors before warnings) and links. `GET .../problems` lists all of them in file order with a cursor, and `GET .../problems.csv` streams them as a CSV with a BOM, where cells that a spreadsheet would run as formulas (`=`, `+`, `-`, `@`, tab, return, except plain numbers) are prefixed with an apostrophe. Counts are always exact; at most 10,000 errors and 10,000 warnings are stored (`truncated` says so).

### Upsert

`INSERT ... ON CONFLICT (sku) DO UPDATE` with 1000 rows per statement. The update sets `deleted_at = NULL` and `version = version + 1`, so soft-deleted products come back with a new version, and it is guarded by `IS DISTINCT FROM` on the imported columns, so rows that already match are untouched: no spurious version or `updated_at` change, and importing the same data twice is a no-op. `image_key` is never touched. Created, updated, restored and unchanged rows are counted per batch from one extra `SELECT` and reported in the import.

### Messaging core (`libs/messaging`)

Generic, with no knowledge of catalog or imports; the envelope and the payload models live in `libs/contracts`.

- **Outbox.** `outbox_table(metadata)` gives each service its own table; `OutboxWriter.add(session, ...)` inserts the envelope in the caller's transaction. `OutboxRelay` sends unpublished rows in order, marks them only after the broker acknowledged them (at-least-once; a crash in between re-sends the same `event_id`) and uses a Postgres advisory lock so a single relay is active and per-key order holds. If Kafka is down the rows wait and leave when it returns (tested against a real broker being stopped and restarted). Published rows are purged after a day.
- **Consumer.** `EventConsumer` commits offsets manually, after the outcome. Handlers are registered per `(event_type, version)`; unknown event types on a shared topic are skipped, an unsupported version of a known type is dead-lettered. Idempotency is a `(consumer_group, event_id)` row in `processed_events`, claimed in the same transaction as the handler (`transactional_handler`) or after it succeeds (`standalone_handler`, for work that runs for minutes and manages its own transactions, like the import, which is safe to repeat thanks to its status guards). Failures are retried with exponential backoff (3 attempts by default); then the original message goes to `<topic>.dlq` with the error, attempt count, original topic, partition, offset and group as headers, and an optional hook runs (the worker marks the import `failed`). Malformed or contract-violating events go straight to the dead letter topic. If the dead letter write itself fails the offset is not committed.
- **Adapters.** Ports (`Publisher`, `MessageSource`) have aiokafka implementations and an in-memory broker, so most tests need no Kafka.
- **Where it runs.** `catalog-worker` is the same image with `python -m catalog.worker`: the relay and the consumer in one process. The API process only writes the outbox, so uploads and confirmations work with Kafka down and `/ready` stays database-only.

## Consequences and limits

- **Memory.** Deduplication keeps one entry per distinct SKU, about 150 bytes each, which is why the file size is capped. A file larger than a few hundred thousand rows needs a bigger limit and more worker memory.
- **CPU in the worker.** The pipeline is pure Python run with `asyncio.to_thread`; it shares the GIL with the relay and the consumer heartbeat. A process pool is the next step if imports get much larger.
- **Two passes per step.** Validation and processing each read the file twice. Reading is cheap compared to parsing, and it avoids persisting a map of winners.
- **Counts after a crash.** If processing restarts after a crash, the counters are recomputed: rows written by the first run now count as unchanged.
- **Source files are kept.** Nothing deletes old uploads or old import rows yet; a retention job belongs with the orphan sweeper noted in ADR 0003.
- **Single partition of work per import.** The message key is the import id, so the two events of an import are ordered; different imports can run in parallel if more workers are started.
- **No "create the missing category and re-validate" action** yet; the report contains the data (grouped unknown names with suggestions) for the backoffice to offer it.
