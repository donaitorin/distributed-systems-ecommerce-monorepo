/**
 * @jest-environment node
 */
import type { ProductSearchState } from "@ecommerce/web-core";
import { isFailure, loadCategories, loadProduct, loadProductPage } from "../src/server/products";
import { CATEGORY, json, mockFetch, problem, product } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ authorization: "Bearer t" }),
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

const STATE: ProductSearchState = {
  q: "shoes",
  category: "sports",
  min_price: "10.50",
  max_price: null,
  in_stock: true,
  sort: "price_asc",
  limit: 12,
  cursor: "abc",
};

describe("loadProductPage", () => {
  it("sends the search state as query parameters", async () => {
    const api = mockFetch([
      {
        method: "GET",
        path: "/api/v1/products",
        respond: () => json({ items: [product()], next_cursor: "n", prev_cursor: null, total: 1, total_exact: true }),
      },
    ]);

    const result = await loadProductPage(STATE);

    expect(isFailure(result)).toBe(false);
    expect(Object.fromEntries(api.calls[0]?.url.searchParams ?? [])).toEqual({
      q: "shoes",
      category: "sports",
      min_price: "10.50",
      in_stock: "true",
      sort: "price_asc",
      limit: "12",
      cursor: "abc",
    });
  });

  it("returns a failure for a rejected cursor", async () => {
    mockFetch([
      {
        method: "GET",
        path: "/api/v1/products",
        respond: () =>
          problem(422, "Validation failed", { errors: [{ location: "query.cursor", message: "does not match", type: "cursor_mismatch" }] }),
      },
    ]);

    const result = await loadProductPage(STATE);

    expect(result).toMatchObject({ ok: false, status: 422, fieldErrors: { cursor: "does not match" } });
  });

  it("redirects to the login page when the session is gone", async () => {
    mockFetch([{ method: "GET", path: "/api/v1/products", respond: () => problem(401, "Unauthorized") }]);

    await expect(loadProductPage(STATE)).rejects.toThrow("NEXT_REDIRECT /login?reason=expired");
  });
});

describe("loadCategories", () => {
  it("returns the categories", async () => {
    mockFetch([{ method: "GET", path: "/api/v1/categories", respond: () => json([CATEGORY]) }]);

    expect(await loadCategories()).toEqual([CATEGORY]);
  });
});

describe("loadProduct", () => {
  it("returns the product with its etag", async () => {
    mockFetch([{ method: "GET", path: "/api/v1/products/RS-001", respond: () => json(product(), 200, { etag: '"3"' }) }]);

    expect(await loadProduct("RS-001")).toEqual({ value: product(), etag: '"3"' });
  });

  it("derives the etag from the version when the header is missing", async () => {
    mockFetch([{ method: "GET", path: "/api/v1/products/RS-001", respond: () => json(product({ version: 9 })) }]);

    expect(await loadProduct("RS-001")).toMatchObject({ etag: '"9"' });
  });

  it("returns a 404 failure", async () => {
    mockFetch([{ method: "GET", path: "/api/v1/products/NOPE", respond: () => problem(404, "Not found") }]);

    expect(await loadProduct("NOPE")).toMatchObject({ ok: false, status: 404 });
  });
});

describe("isFailure", () => {
  it("only recognises failures", () => {
    expect(isFailure({ ok: false })).toBe(true);
    expect(isFailure({ ok: true })).toBe(false);
    expect(isFailure([])).toBe(false);
    expect(isFailure(null)).toBe(false);
  });
});
