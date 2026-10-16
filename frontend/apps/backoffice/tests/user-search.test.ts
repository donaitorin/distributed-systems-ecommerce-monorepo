/**
 * @jest-environment node
 */
import { createLoader } from "nuqs/server";
import { hasUserFilters, toAccountsQuery, userSearchParsers, type UserSearchState } from "../src/lib/user-search";

const load = createLoader(userSearchParsers);
const DEFAULTS: UserSearchState = { email: null, role: null, limit: 25, cursor: null };

describe("user search URL parsing", () => {
  it("uses the defaults for an empty URL", () => {
    expect(load(new URLSearchParams())).toEqual(DEFAULTS);
  });

  it("reads valid values", () => {
    expect(load(new URLSearchParams("email=%20ada&role=admin&limit=100&cursor=abc"))).toEqual({
      email: "ada",
      role: "admin",
      limit: 100,
      cursor: "abc",
    });
  });

  it.each([
    ["email", ""],
    ["email", "x".repeat(255)],
    ["role", "root"],
    ["role", "Admin"],
    ["cursor", ""],
    ["cursor", "c".repeat(513)],
  ])("ignores the invalid %s value %j", (name, value) => {
    expect(load(new URLSearchParams({ [name]: value }))[name as "email"]).toBeNull();
  });

  it.each(["10", "26", "abc", ""])("falls back to 25 for the page size %j", (value) => {
    expect(load(new URLSearchParams({ limit: value })).limit).toBe(25);
  });
});

describe("toAccountsQuery and hasUserFilters", () => {
  it("sends the page size and only what is set", () => {
    expect(toAccountsQuery(DEFAULTS)).toEqual({ limit: 25 });
    expect(toAccountsQuery({ email: "ada", role: "admin", limit: 50, cursor: "n" })).toEqual({
      email: "ada",
      role: "admin",
      limit: 50,
      cursor: "n",
    });
  });

  it("is only active for email and role", () => {
    expect(hasUserFilters({ ...DEFAULTS, limit: 100, cursor: "c" })).toBe(false);
    expect(hasUserFilters({ ...DEFAULTS, email: "a" })).toBe(true);
    expect(hasUserFilters({ ...DEFAULTS, role: "customer" })).toBe(true);
  });
});
