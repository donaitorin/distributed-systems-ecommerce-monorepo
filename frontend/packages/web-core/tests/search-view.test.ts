/**
 * @jest-environment node
 */
import {
  activeFilterChips,
  categoryChoices,
  CLEARED_FILTERS,
  displayedSort,
  loadProductSearch,
  PRICE_ERROR,
  priceFieldError,
  isSearchOutage,
  searchFailureMessage,
  toSearchParams,
  type Failure,
  type ProductSearchState,
} from "../src";

const CATEGORIES = [
  { id: "1", name: "Footwear", slug: "footwear" },
  { id: "2", name: "Toys", slug: "toys" },
];

const EMPTY: ProductSearchState = {
  q: null,
  category: null,
  min_price: null,
  max_price: null,
  in_stock: false,
  sort: null,
  limit: 24,
  cursor: null,
};

const failure = (status: number | null, extra: Partial<Failure> = {}): Failure => ({
  ok: false,
  status,
  title: "Title",
  fieldErrors: {},
  ...extra,
});

describe("reading the search state from the page's search parameters", () => {
  it("repeats array values and skips missing ones", () => {
    const search = toSearchParams({ a: "1", b: ["2", "3"], c: undefined });

    expect(search.getAll("b")).toEqual(["2", "3"]);
    expect(search.has("c")).toBe(false);
  });

  it("ignores invalid values and falls back to the defaults", () => {
    expect(loadProductSearch({ min_price: "abc", limit: "7", sort: "oldest", category: "Not A Slug!" })).toEqual(EMPTY);
  });

  it("reads valid values", () => {
    expect(
      loadProductSearch({ q: " running shoes ", category: "footwear", min_price: "20", in_stock: "true", limit: "48" }),
    ).toEqual({ ...EMPTY, q: "running shoes", category: "footwear", min_price: "20", in_stock: true, limit: 48 });
  });
});

describe("displayedSort", () => {
  it.each([
    [{ q: "shoes", sort: null }, "relevance"],
    [{ q: "shoes", sort: "price_asc" as const }, "price_asc"],
    [{ q: null, sort: null }, "newest"],
    [{ q: null, sort: "relevance" as const }, "newest"],
    [{ q: null, sort: "price_desc" as const }, "price_desc"],
  ])("shows %j as %s", (state, expected) => {
    expect(displayedSort(state)).toBe(expected);
  });
});

describe("categoryChoices", () => {
  it("lists every category after the all option", () => {
    expect(categoryChoices(CATEGORIES, null).map(({ value }) => value)).toEqual(["all", "footwear", "toys"]);
  });

  it("keeps a selected slug that is not in the list so the control does not lie", () => {
    expect(categoryChoices(CATEGORIES, "garden").at(-1)).toEqual({ value: "garden", label: "garden" });
  });
});

describe("priceFieldError", () => {
  it("flags text that is not a price and otherwise passes the server error through", () => {
    expect(priceFieldError("abc", undefined)).toBe(PRICE_ERROR);
    expect(priceFieldError("19.99", "server")).toBe("server");
    expect(priceFieldError("  ", undefined)).toBeUndefined();
  });
});

describe("activeFilterChips", () => {
  it("has no chips without filters", () => {
    expect(activeFilterChips(EMPTY, CATEGORIES)).toEqual([]);
  });

  it("describes each active filter and what removing it changes", () => {
    const chips = activeFilterChips(
      { ...EMPTY, q: "shoes", category: "footwear", min_price: "20", max_price: "150", in_stock: true },
      CATEGORIES,
    );

    expect(chips.map(({ label }) => label)).toEqual([
      "Search: shoes",
      "Category: Footwear",
      "Price: $20 to $150",
      "In stock only",
    ]);
    expect(chips.map(({ patch }) => patch)).toEqual([
      { q: null },
      { category: null },
      { min_price: null, max_price: null },
      { in_stock: false },
    ]);
  });

  it("words one-sided price filters and unknown categories", () => {
    expect(activeFilterChips({ ...EMPTY, min_price: "5" }, CATEGORIES)[0]?.label).toBe("Price: From $5");
    expect(activeFilterChips({ ...EMPTY, max_price: "9.50" }, CATEGORIES)[0]?.label).toBe("Price: Up to $9.50");
    expect(activeFilterChips({ ...EMPTY, category: "garden" }, CATEGORIES)[0]?.label).toBe("Category: garden");
  });

  it("clears every filter and the cursor with CLEARED_FILTERS but keeps the page size", () => {
    expect(CLEARED_FILTERS).toMatchObject({ q: null, category: null, in_stock: false, cursor: null });
    expect("limit" in CLEARED_FILTERS).toBe(false);
  });
});

describe("isSearchOutage", () => {
  it.each([null, 502, 503, 504])("treats %s as an outage", (status) => {
    expect(isSearchOutage(failure(status))).toBe(true);
  });

  it.each([400, 404, 422, 500])("does not treat %s as an outage", (status) => {
    expect(isSearchOutage(failure(status))).toBe(false);
  });
});

describe("searchFailureMessage", () => {
  it.each([
    [failure(422, { fieldErrors: { cursor: "bad" } }), "no longer matches"],
    [failure(422), "not valid"],
    [failure(503), "not available"],
    [failure(502, { detail: "Bad Gateway" }), "not available"],
    [failure(504), "not available"],
    [failure(null), "not available"],
    [failure(500, { detail: "Detail" }), "Detail"],
    [failure(500), "Title"],
  ])("explains %j", (value, text) => {
    expect(searchFailureMessage(value)).toContain(text);
  });
});
