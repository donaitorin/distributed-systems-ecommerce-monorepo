# CSV import

Product import from `data/sample-products.csv`, downloaded on **Thursday 15 October 2026**. The file is committed on purpose and the tests run all of it. Back to the [README](../README.md).

## Import rules

`data/sample-products.csv` (downloaded Thursday 15 October 2026) is committed on purpose: it is seeded with edge cases and the tests run the whole file. The parsing and validation core is pure code in `catalog.domain.csv_import` (no I/O); the upload, confirmation and worker flow is built on top of it (see below).

Required columns are `name`, `sku`, `price` and `stock`; `description`, `category` and `weight_kg` are optional. Column names ignore case and spaces, order does not matter, and unknown or repeated columns reject the file. Row numbers are spreadsheet rows: the header is row 1, and a quoted cell with line breaks is still one row.

| Case in the file | Rule |
| --- | --- |
| Rows with every field empty | Ignored, counted in the report, never an error |
| Empty or whitespace-only name | Error |
| `$29.99` | Read as `29.99`, with a warning. Other formats (`1,299.99`, `29,99`, `12$`, `1e3`) are errors |
| Non-numeric price (`free`), negative price, more than 2 decimals | Error. `0.00` is valid |
| Negative or non-integer stock | Error. `0` and `99999` are valid |
| Empty weight / empty category | Valid, stored as `null` |
| Category that does not exist | Error, never created automatically. Matching ignores case and extra spaces; the report groups unknown names with how many rows they affect and suggests the closest existing one |
| Same SKU in several rows | The last row wins. Every earlier row with different data gets a warning ("replaced by row N"); an earlier row identical to the winner is skipped silently. If the last row is invalid the SKU is not imported |
| Same name, different SKU | Valid: the SKU is the identity |
| HTML or SQL-looking names, commas, quotes, `—`, `™` | Stored literally (real `csv` parser, UTF-8 with BOM detection) |
| Not UTF-8, binary, empty, header only, malformed quoting, missing columns | The whole file is rejected and every document-level problem is reported at once |

Every problem carries the row, the column, the received value and the reason, separated into errors and warnings. The sample file produces:

| Row | Column | Severity | Received | Reason |
| --- | --- | --- | --- | --- |
| 2 | sku | warning | `RS-001` | replaced by row 36, the last row with this SKU |
| 4 | price | warning | `$29.99` | currency symbol removed, read as 29.99 |
| 7 | price | error | `free` | price must be a plain number such as 29.99 |
| 16 | stock | error | `-5` | stock must not be negative |
| 25 | name | error | (empty) | name must not be empty |
| 41 | name | error | (spaces) | name must not be empty |
| 56 | sku | warning | `BS-021` | replaced by row 89, the last row with this SKU |

97 rows = 2 blank + 4 with errors + 3 skipped (rows 2 and 56 replaced by later rows, row 11 identical to the winning row 89) + 88 importable products.

## Importing a CSV

Nothing is written to the catalog until an admin confirms. The file is validated in the background by the `catalog-worker` container, which talks to Kafka; the API itself only needs Postgres and the object store.

```bash
TOKEN=$(make -s dev-token)
curl -s -X POST localhost:8000/api/v1/imports -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/sample-products.csv"                         # 202, status "uploaded"
curl -s localhost:8000/api/v1/imports/<id> -H "Authorization: Bearer $TOKEN"
                                                               # wait for status "validated": counts + first problems
curl -s localhost:8000/api/v1/imports/<id>/problems.csv -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/api/v1/imports/<id>/revalidate -H "Authorization: Bearer $TOKEN"
                                                               # 202, status "uploaded" again: same file, current categories
curl -s -X POST localhost:8000/api/v1/imports/<id>/confirm -H "Authorization: Bearer $TOKEN"
                                                               # 202, status "queued" -> "processing" -> "completed"
curl -s 'localhost:8000/api/v1/products?q=yoga+block'
```

| Status | Meaning |
| --- | --- |
| `uploaded`, `validating` | Stored and hashed; the worker is checking every row |
| `validated` | The report is ready; the admin can fix the file and upload it again, or confirm to import only the valid rows |
| `rejected` | The whole file is unusable (not UTF-8 text, missing columns, ...); every document problem is listed |
| `queued`, `processing` | Confirmed; the worker upserts in batches of 1000 and `progress` grows |
| `completed` | `progress` has the created, updated, restored and unchanged counts |
| `failed` | A worker error survived its retries (the message is in the dead letter topic); `failure_reason` says why |

Uploading the same file twice returns the existing import (`200`), also when it was rejected or has errors. To fix the cause without re-uploading, for example after creating a category the file refers to, `POST /imports/{id}/revalidate` validates the stored file again. It is allowed from `validated` and `rejected` only (`409` once the import is confirmed), discards the previous report, problems and category snapshot in the same transaction that moves the status back to `uploaded` and queues a new `import.validation_requested`, and repeating it while it is pending is harmless (no second event). Rows are upserted by SKU: existing products are updated (and their version bumped only if something changed), soft-deleted ones are restored, and images are never touched. Files are limited by `IMPORT_MAX_BYTES` (50 MB by default). The design, including the reusable messaging library, is in [ADR 0004](adr/0004-csv-import-and-messaging-core.md).
