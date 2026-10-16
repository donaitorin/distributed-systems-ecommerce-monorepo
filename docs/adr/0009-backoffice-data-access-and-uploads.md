# 0009. Backoffice: server-side data access, streaming uploads and URL state

Status: accepted (2026-10-16)

## Context

The backoffice manages the catalog: product list with filters, product create and edit with optimistic concurrency, image upload and, in later parts, categories, CSV import and users. Tokens are in `httpOnly` cookies (ADR 0007), so the browser must never call the API itself.

## Decision

### Data access

- Reads happen in server components and writes in server actions. Both build a typed client from `packages/api-client` that carries the bearer token from the access cookie and the visitor's address as `X-Forwarded-For` (`authorizationHeaders` in `packages/auth`). The gateway stays the only entry point.
- A `401` from the API sends the administrator to the login page with `reason=expired`; a `403` with `reason=forbidden`. Every other failure becomes a plain `Failure` value (status, title, field errors keyed by API field name, `Retry-After`), so forms show the backend's Problem Details in their own words.
- The backend is the authority on validation. The Zod schema in the form mirrors its rules only to give early feedback and to focus the first invalid field. Money and weights stay decimal strings from the input to the request body; they are parsed for display only.
- Client components never import `next/navigation`. They use a small `NavigationContext` (`push`, `refresh`) wired to the real router in the root layout. This keeps them testable and lets Storybook render them: Storybook 10.6's Next mock does not provide the layout context Next 16.4's `useRouter` reads.
- The product images are rendered from the same origin (`/media/...`). `MEDIA_PUBLIC_BASE_URL` defaults to the relative `/media`, so the catalog API returns same-origin image URLs and the CSP's `img-src 'self'` allows them on any host name (`localhost` or `127.0.0.1`). An absolute value still works for a CDN, and then `img-src` has to allow that origin. Before the default changed the API returned `http://127.0.0.1:8000/media/...` and the backoffice rewrote it to a relative path; that rewrite is gone.

### Concurrency

- Edit and delete send `If-Match` with the ETag the page was loaded with; the image endpoints return a new ETag, which the editor adopts, so saving after an upload does not conflict with itself.
- On `412` the server action also fetches the latest product. The dialog lists the fields that differ (a decimal compare, so `59` and `59.00` are equal) and offers two explicit choices: discard the input and load the latest, or keep the input, adopt the latest version number and save again. Dismissing it changes nothing. A `409` on create says the SKU may belong to a deleted product, because the API cannot tell the two cases apart and SKUs of deleted products stay reserved.

### Streaming uploads

- A server action has a small body limit and buffers its input, so uploads go through a route handler, `PUT /admin/api/stream/products/{sku}/image`. The browser sends the multipart body; the handler pipes `request.body` to the gateway with `duplex: "half"` and never parses it.
- The size limit is enforced twice, mirroring the backend (5 MB plus 64 KB of multipart overhead): by `Content-Length` before a byte is read, and by counting bytes in a `TransformStream` when the header is absent or wrong, which errors the stream and aborts the upstream request. Tests prove that an oversized chunked body is rejected after reading about one megabyte of a 256 MB source, and that the happy path hands the gateway a live `ReadableStream`, not a buffer.
- **The routes under `/api/stream/` are excluded from the proxy matcher.** `proxy.ts` (the Next.js middleware) clones the request body so that later handlers can read it, buffering up to `proxyClientMaxBodySize` (10 MB by default) and truncating the rest. That would defeat the streaming and would break the 50 MB CSV import. The routes authenticate themselves with `guardRoute` from `packages/auth`: it verifies and, when needed, refreshes the session like the proxy does, answers `401`, `403` or `503` as `application/problem+json` (a fetch from the page must not follow a redirect to an HTML login page), writes the refreshed cookies on the response, and refuses requests the browser marks `Sec-Fetch-Site: cross-site`.

### URL state

- Search, filters, sort, page size and cursor are `nuqs` parsers built from Zod schemas. An invalid value parses to `null` and is ignored; defaults (page size 24, no availability filter, the sort implied by the presence of `q`) are never written. Every change pushes a history entry and clears the cursor; text inputs keep a local draft and commit to the URL 300 ms after the last keystroke, and only values that pass the schema are committed.
- The page is a server component: it parses the same parsers from `searchParams` and calls `GET /api/v1/products`, so the first render already has results and a pasted URL opens the same search.
- The total is shown by the shared `Pagination`, which says "About N results" when `total_exact` is false and is a status region, so the count is announced when filters change.

### Tests

- All API calls go through the Next.js server, so tests mock `fetch` at the process boundary. MSW, which the project specification mentions, would add a dependency to intercept exactly the same calls; this is a deliberate deviation.

### CSV import

- The file goes through `POST /admin/api/stream/imports`, which is `streamUpload` again: outside `proxy.ts`, guarded by `guardRoute`, `duplex: "half"`, limited to `IMPORT_MAX_BYTES` plus 64 KB of multipart overhead by `Content-Length` and by counting bytes. The backoffice container receives the same `IMPORT_MAX_BYTES` as the catalog, so the browser, the route and the API agree on the limit. Measured against the running stack: a 45 MB file raised the container's memory by 16 MiB, a 90 MB chunked body was answered 413 after about 58 MB had been sent, and a 70 MB `Content-Length` was refused before any body was read.
- Reads for the page go through guarded route handlers (`/admin/api/imports/{id}`, `.../problems`, `.../problems.csv`), not server actions, because TanStack Query polls them from the browser and they answer `application/problem+json` (a redirect to an HTML login page would break a `fetch`). These sit behind `proxy.ts`, which also refreshes the session; the CSV download is streamed through, not buffered. Mutations (confirm, validate again, create a category) are server actions.
- Polling starts at one second and grows by half each time up to eight seconds, counted per status, and stops on `validated`, `rejected`, `completed` and `failed`; confirming or validating again restarts it. A polite live region carries one sentence per status change; the progress bar is not live, so the screen reader is not told about every poll.
- The import id is in the URL (`?import=<id>`), so a reload, a pasted link or the browser's back button reopen the same import. The same file uploaded twice returns the first import (the API answers 200 instead of 202) and the page says so.
- `/admin/products/import` is a static segment, so it wins over `/admin/products/[sku]`. A product whose SKU is `import` would be edited at `/admin/products/IMPORT`; the routes are case sensitive and SKUs are stored upper case, so they never meet.
- "Create category" calls the same server action as the categories page. A category that already exists (`409`) is treated as available, because the next step, validating again, is the same.

## Consequences

- The routes under `/api/stream/` must not be added to the proxy matcher, and any new streaming route has to call `guardRoute`. A test pins the matcher.
- Radix Dialog and Select inject `<style>` elements (the scroll lock and the hidden scrollbar), which the nonce-based `style-src` of ADR 0007 blocks unless they carry the nonce. `StyleNonceProvider` in `packages/ui` hands the nonce to `react-style-singleton` through `get-nonce`'s `setNonce` (a direct dependency of `ui`, pinned to the version Radix already uses) and to `Select.Viewport`, and both layouts read it from the `x-nonce` request header. A CSP nonce belongs to the document, but every client-side navigation renders the layout again with a fresh per-request nonce; the provider therefore keeps the first nonce it received and ignores later ones. `style-src` stays free of `unsafe-inline`.
- Zod 4 probes `new Function("")` to decide whether to compile parsers, and the strict `script-src` reports that probe even though it is caught. `lib/zod-config.ts` turns the JIT off (`jitless`), which costs nothing at the size of these schemas.
- Images and links are same-origin and host-relative, so the backoffice works on both `http://127.0.0.1:8000` and `http://localhost:8000` (cookies are host-only, redirects are relative, media is `/media/...`). `make check-routes` repeats the main checks through `localhost`.
- A product deleted by another administrator while the edit page is open is reported as "no longer exists"; the form is not locked.
