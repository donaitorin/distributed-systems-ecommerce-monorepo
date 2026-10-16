/**
 * @jest-environment node
 */
import { createLoader } from "nuqs/server";
import {
  hasActiveFilters,
  impliedSort,
  productSearchParsers,
  sortToStore,
  toCatalogQuery,
  type ProductSearchState,
} from "../src";

const load = createLoader(productSearchParsers);

const DEFAULTS: ProductSearchState = {
  q: null,
  category: null,
  min_price: null,
  max_price: null,
  in_stock: false,
  sort: null,
  limit: 24,
  cursor: null,
};

describe("product search URL parsing", () => {
  it("uses the defaults for an empty URL", () => {
    expect(load({})).toEqual(DEFAULTS);
  });

  it("reads every valid value", () => {
    const state = load({
      q: "  running shoes ",
      category: "sports-outdoors",
      min_price: "10",
      max_price: "99.99",
      in_stock: "true",
      sort: "price_desc",
      limit: "48",
      cursor: "abc123",
    });

    expect(state).toEqual({
      q: "running shoes",
      category: "sports-outdoors",
      min_price: "10",
      max_price: "99.99",
      in_stock: true,
      sort: "price_desc",
      limit: 48,
      cursor: "abc123",
    });
  });

  it.each([
    ["q", "", "q"],
    ["q", "x".repeat(101), "q"],
    ["category", "Not A Slug", "category"],
    ["category", "-leading", "category"],
    ["min_price", "abc", "min_price"],
    ["min_price", "1.234", "min_price"],
    ["min_price", "-5", "min_price"],
    ["max_price", "12345678901", "max_price"],
    ["sort", "popularity", "sort"],
    ["cursor", "", "cursor"],
    ["cursor", "c".repeat(513), "cursor"],
  ] as const)("ignores the invalid %s value %j", (name, value, key) => {
    expect(load({ [name]: value })[key]).toBeNull();
  });

  it.each(["7", "100", "abc", "24.5", ""])("falls back to the default page size for %j", (value) => {
    expect(load({ limit: value }).limit).toBe(24);
  });

  it("treats an unknown availability value as not filtering", () => {
    expect(load({ in_stock: "maybe" }).in_stock).toBe(false);
  });

  it("does not write defaults into the URL", () => {
    const parsers = productSearchParsers;

    expect(parsers.limit.eq(24, parsers.limit.defaultValue)).toBe(true);
    expect(parsers.in_stock.eq(false, parsers.in_stock.defaultValue)).toBe(true);
    expect(parsers.limit.serialize(48)).toBe("48");
  });
});

describe("toCatalogQuery", () => {
  it("sends only what is set, with the page size always present", () => {
    expect(toCatalogQuery(DEFAULTS)).toEqual({ limit: 24 });
  });

  it("sends every filter and keeps prices as decimal strings", () => {
    expect(
      toCatalogQuery({
        q: "shoes",
        category: "sports",
        min_price: "10.50",
        max_price: "99",
        in_stock: true,
        sort: "price_asc",
        limit: 12,
        cursor: "next",
      }),
    ).toEqual({
      q: "shoes",
      category: "sports",
      min_price: "10.50",
      max_price: "99",
      in_stock: true,
      sort: "price_asc",
      limit: 12,
      cursor: "next",
    });
  });
});

describe("sorting defaults", () => {
  it("shows newest without a query and best match with one", () => {
    expect(impliedSort({ q: null, sort: null })).toBe("newest");
    expect(impliedSort({ q: "shoes", sort: null })).toBe("relevance");
    expect(impliedSort({ q: "shoes", sort: "newest" })).toBe("newest");
  });

  it("does not store the implied sort but stores an explicit different one", () => {
    expect(sortToStore("newest", null)).toBeNull();
    expect(sortToStore("relevance", "shoes")).toBeNull();
    expect(sortToStore("newest", "shoes")).toBe("newest");
    expect(sortToStore("price_asc", null)).toBe("price_asc");
  });
});

describe("hasActiveFilters", () => {
  it("is false for the defaults, sort, page size and cursor", () => {
    expect(hasActiveFilters({ ...DEFAULTS, sort: "price_asc", limit: 48, cursor: "c" })).toBe(false);
  });

  it.each([{ q: "a" }, { category: "c" }, { min_price: "1" }, { max_price: "2" }, { in_stock: true }])(
    "is true when %j is set",
    (patch) => {
      expect(hasActiveFilters({ ...DEFAULTS, ...patch })).toBe(true);
    },
  );
});
