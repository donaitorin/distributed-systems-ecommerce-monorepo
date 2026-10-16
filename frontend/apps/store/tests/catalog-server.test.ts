/**
 * @jest-environment node
 */
import { isFailure, type ProductSearchState } from "@ecommerce/web-core";
import { loadCategories, loadProduct, loadProductPage } from "../src/server/catalog";
import { CATEGORY, json, mockFetch, problem, product, productPage } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ "x-forwarded-for": "203.0.113.7" }),
}));

const STATE: ProductSearchState = {
  q: "runing shoes",
  category: "footwear",
  min_price: "20",
  max_price: null,
  in_stock: true,
  sort: "price_asc",
  limit: 12,
  cursor: "abc",
};

describe("loadProductPage", () => {
  it("sends the search state to the catalog through the gateway with the visitor's address", async () => {
    const api = mockFetch([{ method: "GET", path: "/api/v1/products", respond: () => json(productPage()) }]);

    const result = await loadProductPage(STATE);

    expect(isFailure(result)).toBe(false);
    expect(Object.fromEntries(api.calls[0]?.url.searchParams ?? [])).toEqual({
      q: "runing shoes",
      category: "footwear",
      min_price: "20",
      in_stock: "true",
      sort: "price_asc",
      limit: "12",
      cursor: "abc",
    });
    expect(new Headers(api.calls[0]?.init.headers).get("x-forwarded-for")).toBe("203.0.113.7");
  });

  it("returns a failure instead of throwing when the catalog answers an error", async () => {
    mockFetch([{ method: "GET", path: "/api/v1/products", respond: () => problem(503, "Search timed out") }]);

    expect(await loadProductPage(STATE)).toMatchObject({ ok: false, status: 503 });
  });

  it("returns a failure when the gateway cannot be reached", async () => {
    global.fetch = jest.fn(() => Promise.reject(new TypeError("fetch failed")));

    expect(await loadProductPage(STATE)).toMatchObject({ ok: false, status: null });
  });
});

describe("loadCategories", () => {
  it("returns the categories", async () => {
    mockFetch([{ method: "GET", path: "/api/v1/categories", respond: () => json([CATEGORY]) }]);

    expect(await loadCategories()).toEqual([CATEGORY]);
  });
});

describe("loadProduct", () => {
  it("reads a product by SKU, URL-encoding the path", async () => {
    const api = mockFetch([{ method: "GET", path: /^\/api\/v1\/products\//, respond: () => json(product()) }]);

    expect(await loadProduct("RS 001")).toMatchObject({ sku: "RS-001" });
    expect(api.calls[0]?.url.pathname).toBe("/api/v1/products/RS%20001");
  });

  it("reports an unknown or retired product as a 404 failure", async () => {
    mockFetch([{ method: "GET", path: /^\/api\/v1\/products\//, respond: () => problem(404, "Product not found") }]);

    expect(await loadProduct("NOPE-1")).toMatchObject({ ok: false, status: 404 });
  });
});
