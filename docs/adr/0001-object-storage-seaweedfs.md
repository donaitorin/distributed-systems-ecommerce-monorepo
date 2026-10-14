# 0001. Object storage: SeaweedFS behind an S3 port

Status: accepted (2026-10-14)

## Context

Catalog stores product images and uploaded CSV files. We need an S3 compatible object store that runs inside `docker compose up`, so a reviewer can clone the repository and start everything with one command.

The original plan used MinIO. MinIO Community was archived in April 2026 and its images were removed from Docker Hub. Depending on it would mean pinning to an unmaintained project, with no security fixes and no way to pull a pinned image.

## Decision

Use SeaweedFS (`chrislusf/seaweedfs`, pinned to an exact version) as a single container with the S3 gateway enabled. The service is named `object-storage` and every setting uses the `OBJECT_STORAGE_*` prefix, so nothing in the code or configuration names the vendor.

- Credentials come from `.env` and are rendered into SeaweedFS's S3 identity configuration at container start.
- A one-shot job (`object-storage-init`, `amazon/aws-cli`, pinned) creates the `media` and `imports` buckets.
- `media` allows anonymous object reads but no listing, writing or deleting. This is the identity `anonymous` with the action `Read:media`. `imports` is private.
- The S3 API is published on `127.0.0.1:19000` for host development. There is no console.

The anonymous behavior was verified against SeaweedFS 4.48: an anonymous GET of a `media` object returns 200, while listing `media`, reading `imports`, listing buckets, PUT and DELETE return 403.

## Alternatives considered

| Option | Why not |
| --- | --- |
| MinIO image from Quay | Same archived project: no upstream security fixes. We could not find a pinnable official tag when this was evaluated |
| Build MinIO from source | A custom Dockerfile and build step for every reviewer, and we would own patching of an archived project |
| Chainguard MinIO image | Ties the repository to a third-party vendor's image catalog and access terms for a component that is meant to be replaceable |
| Garage | Actively maintained and lightweight, but not evaluated in depth: its S3 feature coverage and anonymous read model would need checking against our `/media` flow |
| RustFS | Newer S3 compatible store; not evaluated in depth and with a shorter track record |
| SeaweedFS (chosen) | Actively maintained, official pinned image, S3 API with per-identity actions that express "read objects, no listing" directly |

## Consequences

- Application code only knows the `ObjectStorage` port in `libs/storage` (`put`, `delete`, `public_url`) and its S3 adapter (boto3). The adapter talks plain S3, so it works the same against SeaweedFS and AWS S3.
- Moving to AWS S3 is configuration only: drop `OBJECT_STORAGE_ENDPOINT`, set real credentials and bucket names, and point `MEDIA_PUBLIC_BASE_URL` at CloudFront or the bucket. The database stores object keys, never URLs, so no data migration is needed.
- Tests use an in-memory adapter, so no test depends on SeaweedFS.
- Anonymous read rules are SeaweedFS specific. On AWS they become a bucket policy or a CloudFront origin access rule; that lives in infrastructure, not in application code.
- SeaweedFS is less widely known than MinIO, so the README documents how to inspect it (`aws s3 ls --endpoint-url http://127.0.0.1:19000`).
