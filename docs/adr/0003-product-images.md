# 0003. Product images: validated uploads, WebP renditions and storage that never blocks readiness

Status: accepted (2026-10-15)

## Context

Products can have one optional image. Admins upload it through the catalog API, the storefront shows a 400 px thumbnail in listings and a 1200 px image on the detail page. Files live in object storage behind the `ObjectStorage` port (ADR 0001); the database is the source of truth for which objects belong to a product.

## Decision

### API

- `PUT /api/v1/products/{sku}/image` takes a multipart body with one `file` part. `DELETE /api/v1/products/{sku}/image` removes the image. Both are admin only, require `If-Match` and bump the product version, because changing the image changes the product. Both answer `200` with the product and its new `ETag`, since the client needs the new version.
- Products expose two optional fields, `image_url` (1200 px) and `thumbnail_url` (400 px). Both are `null` without an image. The fields are additive, so existing clients are unaffected.
- `DELETE` on a product without an image is `404`.
- Errors are Problem Details: `413` above 5 MB, `415` when the body is not multipart or the content is not a JPEG, PNG or WebP, `422` for a missing or duplicated `file` part, a corrupt image or an image over 25 megapixels, `503` with `Retry-After` when object storage fails.
- The order of checks avoids wasted work: authentication, `If-Match` presence, then `404`/`412` before the body is read, then validation.

### Validation and processing

- The format is decided by magic bytes (JPEG, PNG, RIFF/WEBP), never by file name or `Content-Type`. A text file named `photo.jpg` is a `415`, and a PNG uploaded as `photo.txt` is accepted.
- The upload is read as a stream with `python-multipart`'s parser. Starlette's own form parsing would spool the whole body to disk before the handler runs, so it cannot enforce a limit while reading. Here at most 5 MB plus one chunk is held in memory, a declared `Content-Length` over the limit is refused without reading, a body that is not an image is abandoned after its first 12 bytes, and a body without its closing boundary is rejected.
- Pillow runs in a worker thread (`asyncio.to_thread`) behind a semaphore of 2: decoding a 25 megapixel RGBA image takes about 100 MB, so unbounded parallel uploads could exhaust memory.
- Decompression bombs: the pixel count is read from the header and compared with 25,000,000 before any decoding, and Pillow's own `MAX_IMAGE_PIXELS` is set to the same value so absurd headers fail at open.
- EXIF orientation is applied to the pixels, then every rendition is re-encoded from a bare RGB or RGBA image, so EXIF (including GPS), XMP and **ICC profiles are dropped**. Dropping the profile can shift colors of wide-gamut sources slightly; converting to sRGB first with `ImageCms` would avoid that and is left out on purpose to keep the pipeline simple. Tests inspect the output bytes to prove nothing survives.
- Sizes mean the longest side (400 and 1200), aspect ratio is kept, images are never upscaled (a smaller source keeps its size in both renditions), transparency is preserved and animated inputs keep their first frame. WebP quality is 82.

### Keys

`products.image_key` stores the key **stem** `products/{SKU}/{uuid}`, and renditions are `{stem}-400.webp` and `{stem}-1200.webp`. It is never a URL; `MEDIA_PUBLIC_BASE_URL` is applied when answering. A new image always has a new UUID, so the objects are immutable and are stored with `Cache-Control: public, max-age=31536000, immutable`. Verified against SeaweedFS 4.48: the header is stored and returned on anonymous `GET` and `HEAD`.

### Consistency between storage and the database

Object storage and PostgreSQL cannot share a transaction, so the order is chosen so that a failure never leaves a product pointing at missing objects:

1. Check the SKU and version without a lock (cheap early `404`/`412`).
2. Upload both new renditions. If the first or second upload fails, delete what was uploaded.
3. In one short transaction lock the row, re-check `If-Match`, set the new key, bump the version and commit. The row lock is deliberately **not** held during uploads. If this step fails for any reason (including a conflict that appeared while uploading, or cancellation of the request), the new objects are deleted.
4. Only after the commit succeeds, delete the old objects. A failure here is logged as a warning (`image cleanup failed`, with the key) and does not fail the request.

`DELETE` follows the same rule: clear the key and commit first, then delete the objects.

**Orphans still to handle.** Two situations leave objects that no product references: a process crash between steps 2 and 3, and a failed delete in step 4. A sweeper is needed later (a CLI under `catalog.tools`, or a periodic job). It needs `list(prefix)` on the `ObjectStorage` port, and it should delete only keys under `products/` that no row references and that are older than a grace period (for example one hour), so it never races an upload in flight. Soft-deleting a product keeps its images on purpose, because the product can be restored.

### Object storage is not part of `/ready`

`/ready` answers "should traffic be routed to this instance". Storage only affects the two image endpoints; search, browsing and the cart's catalog calls do not touch it. Failing readiness over a down bucket would turn a partial outage into a full one, and the service rule is that a service must be ready with only its own database up. So the S3 client is created lazily, catalog starts and stays ready without storage, and the image endpoints answer `503` with `Retry-After: 1` and a warning in the log with the request id. Clients use bounded timeouts (3 s connect, 15 s read, two attempts) so a dead endpoint cannot hold a request for a minute. Storage health belongs in metrics, not in readiness (metrics are listed as future work in the README). Removing an image still succeeds when storage is down, because the database change is what matters and the objects become orphans for the sweeper.

### Gateway

Traefik routes ``PathPrefix(`/media/`)`` for `GET` and `HEAD` only to `object-storage:8333`. Because requests use path-style S3, `/media/<key>` is already bucket `media`, key `<key>`, so no rewrite is needed. The trailing slash keeps the bucket listing unrouted, and the anonymous identity cannot list or write anyway (both verified by the integration tests).

## Consequences

- New dependencies in catalog: Pillow, `python-multipart` and the workspace library `ecommerce-storage`.
- The `ObjectStorage.put` port gained an optional `cache_control`, and storage adapters raise `ObjectStorageError` instead of leaking boto3 exceptions.
- The S3 adapter is now tested against a real SeaweedFS (Testcontainers, the pinned image from `docker-compose.yml` and the real `start.sh`), not only with botocore stubs.
- Replacing an image costs two uploads and up to two deletes per request; browsers cache each URL forever.
- Direct-to-bucket uploads with presigned URLs remain the path for much higher volume, as the spec already notes.
