# 0010. Store: catalog search, product pages and shared search logic

Status: accepted (2026-10-16)

## Context

The storefront needs a searchable catalog with shareable links, a product page that search engines can read, and an accessible filter experience on phones. The backoffice already solved URL state, server-side data access and the CSP nonce for its own product list (ADR 0007 and 0009), and both apps must keep one behavior for the same search parameters.

## Decision

### Routes

- `/products` is the search page and `/products/{sku}` the product page. `/` redirects to `/products` with a temporary redirect (307) that keeps the query string, so it can become a landing page later without anything cached as permanent.
- Both are server components. They read the search parameters, call the catalog through the gateway (public endpoints; the visitor's address is still forwarded for rate limiting) and render the first page of results in the HTML. Because every response carries a nonce (ADR 0007), they are rendered per request.
- Unknown and retired SKUs call `notFound()`. The page has no `loading.tsx` above it on purpose: a streamed shell would be sent before the page can decide, and the response would be `200` with a "not found" body. Without it the answer is a real `404` (checked by `make check-routes`).
- The SKU is case-insensitive in the API. A request in another case is redirected (307) to the canonical SKU, and the page declares a canonical link, so a product has one address.
- A temporary failure (503, network) is not a 404: the page shows an alert with a retry link and is marked `noindex`.

### Search state

- The parsers, the URL loader, the sort and category choices, the filter chips and the failure messages live in `packages/web-core` and are used by both apps. The backoffice was switched to them, so the two search pages cannot drift apart.
- History entries, the 300 ms debounce, cleared cursors and unwritten defaults are the same as in ADR 0009. The store adds: best match is only offered (and shown) while there is a search text, because the API falls back to newest without one; pagination scrolls to the top; results pages with a search text, filters or a cursor are `noindex, follow`, the plain listing is indexable.
- The search box is not part of the filters. It stays visible, and the filters (category, price, availability) live in a sidebar from `lg` and in a drawer below. Both render the same fields component. The drawer content only exists while it is open, the sidebar is hidden with CSS on small screens, and both read and write the same URL, so they can never disagree.
- Removing a chip, or clearing all filters, moves focus to the search box: the chip that had focus is about to disappear when the page re-renders.

### Accessibility choices

- The drawer is the existing `Modal` with `variant="drawer"` (Radix Dialog): focus trap, Escape, and focus returned to the opener are Radix's, plus the opener bookkeeping the modal already had.
- There is one live region for the result count: the one in `Pagination`. A second `role="status"` for the same number would be announced twice, so the count above the grid is plain text.
- A chip's accessible name is "Remove filter: " plus its visible text, so the visible label is contained in the name (WCAG 2.5.3).
- `ProductImage` checks `complete` and `naturalWidth` when it mounts, because an image that fails while the page is still hydrating fires `error` before React listens.

### Add to cart

`AddToCartSlot` renders a notice for out of stock products (visible, not purchasable) and an empty element with the id `add-to-cart-slot` otherwise. The cart stage replaces the body of that component; nothing else in the page has to change.

## Consequences

- Moving between `/products` and a product page is a full page load (plain links, as in the backoffice), which the dynamic rendering of ADR 0007 already implies.
- The store has the same dependencies as the backoffice for URL state (`nuqs`) and none for forms yet; `react-hook-form`, `zod` resolvers and the session UI arrive with the customer authentication stage.
- Test files that render these components need `globalThis.Request`, which jsdom lacks and nuqs's server loader checks for; the store's Jest setup defines it once.

## Customer authentication and account (added with the customer accounts stage)

- **One redirect helper.** `nextPath(candidate, { fallback, loopPaths, zonePath? })` in `web-core` replaces the backoffice's own helper. It builds on `safeRedirectPath` (internal paths only, no `//`, backslashes or control characters), strips the zone prefix when there is one, and refuses the pages that would loop (the login and register pages). The backoffice and the store only supply their fallback and paths, and the open-redirect cases are tested once in `web-core` and again through each app's configuration.
- **Shared messages and focus.** The credential messages (incorrect credentials, rate limit wording, required fields) and the plain-language password rules moved to `web-core`; the effect that moves focus to the first invalid field, or to the error alert, is a hook there too. The password rules are mapped from the API's error codes (`too_short`, `too_common`, `same_as_email`, `too_long`), not from its English text, so a reworded backend message cannot leak into the form.
- **Register then sign in.** The sign up action registers, then signs in with the same credentials and redirects. If signing in fails afterwards the form says the account exists and asks the customer to sign in, instead of reporting a failed sign up. A taken email (409) is an email field error, which is the documented trade-off of ADR 0005.
- **Rate limits.** `registerAccount` now returns `Retry-After` like `signIn`, so the 429 message can say when to try again. The limits themselves are the gateway's (ADR 0008).
- **Sessions in the header.** The root layout reads the session and shows Sign in to a visitor and Account plus Sign out to a customer. Signing out returns to `/products`. A signed in customer who opens `/login` or `/register` is sent on to the next page (an expired session is the exception, so the notice stays visible).
- **Profile.** `/account` is protected by the proxy and by `requireSession`. The profile form uses React Hook Form with Zod for early feedback, the server action validates again, and the API stays the authority: its field errors are shown on the fields, with the phone one worded in plain language. A blank phone is sent as `null`, which clears it. A `401` from the accounts API sends the customer to the login page with `reason=expired` and back to `/account` afterwards.
- **Search box.** Pressing Enter applies the search text immediately and cancels the pending 300 ms debounce (`useUrlText` returns a third `commitNow` function; the backoffice filters can adopt it the same way).
