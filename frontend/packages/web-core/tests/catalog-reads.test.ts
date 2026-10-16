/**
 * @jest-environment node
 */
import { createApiClient, type CatalogPaths } from "@ecommerce/api-client";
import { fetchCategories, fetchProductPage, isFailure, settle, type ProductSearchState } from "../src";

const STATE: ProductSearchState = {
  q: "shoes",
  category: "footwear",
  min_price: null,
  max_price: "100",
  in_stock: true,
  sort: null,
  limit: 12,
  cursor: "abc",
};

function apiReturning(body: unknown, status = 200) {
  const calls: URL[] = [];
  const fetchStub = jest.fn((input: Request | URL | string) => {
    calls.push(new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url));
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": status === 200 ? "application/json" : "application/problem+json" },
      }),
    );
  });
  return { api: createApiClient<CatalogPaths>({ baseUrl: "http://gateway.test", fetch: fetchStub as typeof fetch }), calls };
}

describe("catalog reads", () => {
  it("sends the search state as query parameters and returns the page", async () => {
    const page = { items: [], next_cursor: null, prev_cursor: null, total: 0, total_exact: true };
    const { api, calls } = apiReturning(page);

    expect(await fetchProductPage(api, STATE)).toEqual(page);
    expect(Object.fromEntries(calls[0]?.searchParams ?? [])).toEqual({
      q: "shoes",
      category: "footwear",
      max_price: "100",
      in_stock: "true",
      limit: "12",
      cursor: "abc",
    });
  });

  it("returns the categories", async () => {
    const { api, calls } = apiReturning([{ id: "1", name: "Toys", slug: "toys" }]);

    expect(await fetchCategories(api)).toHaveLength(1);
    expect(calls[0]?.pathname).toBe("/api/v1/categories");
  });

  it("settles an API error into a failure and passes results through", async () => {
    const { api } = apiReturning({ type: "about:blank", title: "Down", status: 503 }, 503);

    const failed = await settle(() => fetchCategories(api));

    expect(isFailure(failed)).toBe(true);
    expect(failed).toMatchObject({ status: 503, title: "Down" });
    expect(await settle(() => Promise.resolve([1]))).toEqual([1]);
    expect(isFailure(null)).toBe(false);
    expect(isFailure("x")).toBe(false);
  });
});
