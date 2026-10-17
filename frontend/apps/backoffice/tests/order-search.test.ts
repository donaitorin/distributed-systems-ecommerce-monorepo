/**
 * @jest-environment node
 */
import { createLoader } from "nuqs/server";
import { dateRangeError, hasOrderFilters, orderSearchParsers, RANGE_ERROR, toOrdersQuery, type OrderSearchState } from "../src/lib/order-search";

const load = createLoader(orderSearchParsers);
const DEFAULTS: OrderSearchState = { status: null, from: null, to: null, limit: 25, cursor: null };

describe("order search URL parsing", () => {
  it("uses the defaults for an empty URL", () => {
    expect(load(new URLSearchParams())).toEqual(DEFAULTS);
  });

  it("reads valid values", () => {
    expect(load(new URLSearchParams("status=CANCELLED&from=2026-10-01&to=2026-10-17&limit=100&cursor=abc"))).toEqual({
      status: "CANCELLED",
      from: "2026-10-01",
      to: "2026-10-17",
      limit: 100,
      cursor: "abc",
    });
  });

  it.each([
    ["status", "SHIPPED"],
    ["status", "confirmed"],
    ["from", "abc"],
    ["from", "2026-13-01"],
    ["from", "2026-02-30"],
    ["from", "2026-10-1"],
    ["from", "2026-10-17T10:00:00Z"],
    ["to", ""],
    ["cursor", ""],
    ["cursor", "c".repeat(513)],
  ])("ignores the invalid %s value %j", (name, value) => {
    expect(load(new URLSearchParams({ [name]: value }))[name as "status"]).toBeNull();
  });

  it.each(["10", "26", "abc", ""])("falls back to 25 for the page size %j", (value) => {
    expect(load(new URLSearchParams({ limit: value })).limit).toBe(25);
  });
});

describe("toOrdersQuery", () => {
  it("sends only the page size for no filters", () => {
    expect(toOrdersQuery(DEFAULTS)).toEqual({ limit: 25 });
  });

  it("turns the days into a half open UTC range: the end day is included", () => {
    expect(toOrdersQuery({ ...DEFAULTS, status: "PAID", from: "2026-10-01", to: "2026-10-17", cursor: "c", limit: 50 })).toEqual({
      status: "PAID",
      created_from: "2026-10-01T00:00:00Z",
      created_to: "2026-10-18T00:00:00Z",
      limit: 50,
      cursor: "c",
    });
  });

  it("rolls the end day over a month and a year", () => {
    expect(toOrdersQuery({ ...DEFAULTS, to: "2026-10-31" }).created_to).toBe("2026-11-01T00:00:00Z");
    expect(toOrdersQuery({ ...DEFAULTS, to: "2026-12-31" }).created_to).toBe("2027-01-01T00:00:00Z");
    expect(toOrdersQuery({ ...DEFAULTS, to: "2028-02-28" }).created_to).toBe("2028-02-29T00:00:00Z");
  });

  it("accepts a single day as a range of that day", () => {
    expect(toOrdersQuery({ ...DEFAULTS, from: "2026-10-17", to: "2026-10-17" })).toMatchObject({
      created_from: "2026-10-17T00:00:00Z",
      created_to: "2026-10-18T00:00:00Z",
    });
  });
});

describe("dateRangeError and hasOrderFilters", () => {
  it("rejects an end before the start only", () => {
    expect(dateRangeError({ from: "2026-10-17", to: "2026-10-16" })).toBe(RANGE_ERROR);
    expect(dateRangeError({ from: "2026-10-17", to: "2026-10-17" })).toBeNull();
    expect(dateRangeError({ from: "2026-10-17", to: null })).toBeNull();
    expect(dateRangeError({ from: null, to: "2026-10-01" })).toBeNull();
  });

  it("knows when a filter is active, ignoring the cursor", () => {
    expect(hasOrderFilters(DEFAULTS)).toBe(false);
    const onLaterPage: OrderSearchState = { ...DEFAULTS, cursor: "c", limit: 100 };
    expect(hasOrderFilters(onLaterPage)).toBe(false);
    expect(hasOrderFilters({ ...DEFAULTS, status: "PAID" })).toBe(true);
    expect(hasOrderFilters({ ...DEFAULTS, from: "2026-10-01" })).toBe(true);
    expect(hasOrderFilters({ ...DEFAULTS, to: "2026-10-01" })).toBe(true);
  });
});
