# 0007. Frontend: Multi-Zones, cookie sessions and a strict nonce-based CSP

Status: accepted (2026-10-15)

## Context

The storefront and the backoffice have different users, release rhythm and risk, and both must live under one domain. Sessions use the access and refresh tokens that the auth service issues (ADR 0005). Product names, CSV content and other user-controlled text end up in pages, so a script injection must not be able to run.

## Decision

### Two zones behind the gateway

- `apps/store` serves `/` and `apps/backoffice` serves `/admin` (`basePath` and `assetPrefix` are both `/admin`, so its assets are under `/admin/_next/...` and never collide with the store's `/_next/...`).
- The gateway routes `/admin` and `/admin/*` to the backoffice and everything else, at the lowest priority, to the store. Every API, docs and media router has a higher priority. `make check-routes` proves it against the running stack.
- Module Federation was rejected (weak App Router support); one app with route groups was rejected because it is not a micro frontend. The cost of Multi-Zones is a full page load when moving between zones and sharing code at build time only (`packages/ui`, `packages/auth`, `packages/api-client`).
- Each zone is its own image, with its own build, and starts and passes its health check without any backend. The store pages for authentication live at `/login`, `/register` and `/account`, never under `/auth` (the gateway reserves `/auth/*` for the auth service docs).

### Sessions

- Access and refresh tokens are in `httpOnly`, `SameSite=Lax` cookies (`Secure` by default, `AUTH_COOKIE_SECURE=false` for local http), path `/`, so both zones receive them. Nothing is in `localStorage`.
- `proxy.ts` (the Next.js 16 name of `middleware.ts`) verifies the access token with `jose` against the cached JWKS, refreshes an expired session, hands the new cookies to the page of the same request, and applies the role guard. The backoffice requires `admin`; a customer is sent to the login page with `reason=forbidden`; with the JWKS or the API unreachable the answer is `503` with `Retry-After`, never an anonymous pass.
- Server components only read and verify the access cookie. They cannot set cookies, so refreshing happens in the proxy, in server actions and in route handlers.

### Content Security Policy

- Every page response carries a per-request nonce policy: `script-src 'self' 'nonce-…' 'strict-dynamic'`, no `unsafe-inline` for scripts, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri` and `form-action` limited to `'self'`, and `font-src 'self'` (fonts are self-hosted with Fontsource, so no external origin is needed). `style-src-attr 'unsafe-inline'` is allowed because Radix positions popovers with style attributes. `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` and `Permissions-Policy` are static headers on every route. `upgrade-insecure-requests` is left out because it would break plain-http local runs; HSTS belongs to the TLS terminator in front of the gateway.
- **Consequence: every page is rendered dynamically.** A nonce must be unique for each response and Next.js stamps it into its own scripts while rendering, so a prerendered or cached page cannot carry a valid nonce. The root layouts call `connection()` to opt out of static generation, and the build output marks every route as dynamic (`ƒ`). There is no static generation or ISR for HTML.
- **Why that is acceptable here:** catalog pages depend on search parameters, stock, price and the session, so they are dynamic anyway; the HTML is still server-rendered, so SEO and first paint are unaffected; static assets keep long-lived immutable caching; and the cost is server CPU per page view, which one Node process handles at this scale. If load makes it a problem, the options are a hash-based policy for static pages, partial prerendering, or caching rendered fragments, not weakening the script policy.

### Refresh races

- Two requests of one session can refresh with the same token at the same time. The auth service answers the loser with `401` inside a 10 second grace window (ADR 0005). The Next.js side shares the result: refreshes are deduplicated per token fingerprint for 10 seconds, and a rejected refresh gets one retry with the newest cookie.
- **Limit:** that deduplication is in memory, so it only works inside one Next.js process. With several replicas of a zone, two requests landing on different replicas still race, the loser's refresh is rejected, and that session is signed out. Before running more than one replica, keep the rotated pair in a shared store for the length of the grace window, for example in `redis-cache` under the token fingerprint with a 10 second TTL (the value is a token pair, so it needs the same care as the cookies), or route a session to one replica.

### Toolchain choices that surprise

- TypeScript 6.0 and ESLint 9: typescript-eslint requires TypeScript below 6.1, TypeScript 7 has no classic compiler API (the comment checker needs it), and `eslint-plugin-jsx-a11y` supports ESLint up to 9.
- Jest stays the unit test runner. Jest 30 cannot load the ESM-only `jose` from `node_modules`, so the auth package transforms it.
- The **Storybook test runner is deprecated** (Storybook prints that its support has ended) and is kept on purpose: it runs axe on every story with the WCAG 2.0 to 2.2 A and AA rule sets, it is what the project spec asks for, and it is stable. It also fails when a `.storybook/test-runner.*` file exists (Storybook's loader calls `module.register()`, which Jest 30 blocks), so the axe hooks are registered from `.storybook/test-runner-jest.config.mjs`. `make test-storybook` always serves its own static build on port 6107 so it can never hit a running `storybook dev`. **Migration path:** the Storybook Vitest addon (`@storybook/addon-vitest`) with the a11y addon running in browser mode; stories and their `play` functions stay as they are, only the runner and its axe configuration change.

## Consequences

- The strict policy and the per-request rendering are a deliberate price for blocking injected scripts.
- A zone cannot be deployed with more than one replica without the shared refresh store described above.
- Deprecated Storybook tooling is a known, documented debt with a defined exit.
