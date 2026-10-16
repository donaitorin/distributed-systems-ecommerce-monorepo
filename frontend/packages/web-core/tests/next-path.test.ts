/**
 * @jest-environment node
 */
import { nextPath, type NextPathOptions } from "../src";

const STORE: NextPathOptions = { fallback: "/products", loopPaths: ["/login", "/register"] };
const ZONE: NextPathOptions = { fallback: "/", loopPaths: ["/login"], zonePath: "/admin" };

const HOSTILE: readonly (readonly [string, string])[] = [
  ["an absolute URL", "https://evil.example/phish"],
  ["a protocol relative URL", "//evil.example"],
  ["backslashes", "/\\evil.example"],
  ["a javascript URL", "javascript:alert(1)"],
  ["a data URL", "data:text/html,<script>alert(1)</script>"],
  ["a scheme without slashes", "http:evil.example"],
  ["a relative path", "products"],
  ["a tab inside the path", "/\t/evil.example"],
  ["a newline inside the path", "/\n/evil.example"],
  ["an empty value", ""],
];

describe.each([
  ["a plain zone", STORE, "/products"],
  ["a zone with a prefix", ZONE, "/"],
])("nextPath for %s", (_name, options, fallback) => {
  it.each(HOSTILE)("falls back for %s", (_label, candidate) => {
    expect(nextPath(candidate, options)).toBe(fallback);
  });

  it.each([null, undefined])("falls back for %s", (candidate) => {
    expect(nextPath(candidate, options)).toBe(fallback);
  });

  it.each(["/login", "/login?next=%2Fcart", "/login/", "/login#top"])("never sends the visitor back to %s", (candidate) => {
    expect(nextPath(candidate, options)).toBe(fallback);
  });
});

describe("nextPath for the store", () => {
  it.each([
    ["/account", "/account"],
    ["/products?q=shoes&sort=newest", "/products?q=shoes&sort=newest"],
    ["/products/RS-001", "/products/RS-001"],
    ["/", "/"],
    ["/loginx", "/loginx"],
  ])("keeps the internal path %s", (candidate, expected) => {
    expect(nextPath(candidate, STORE)).toBe(expected);
  });

  it.each(["/register", "/register?next=%2Faccount"])("does not loop through %s", (candidate) => {
    expect(nextPath(candidate, STORE)).toBe("/products");
  });
});

describe("nextPath inside a zone", () => {
  it.each([
    ["/admin", "/"],
    ["/admin/", "/"],
    ["/admin/products", "/products"],
    ["/admin/products?q=a", "/products?q=a"],
    ["/admin?x=1", "/?x=1"],
    ["/products", "/products"],
  ])("removes the zone prefix, which the router adds back: %s", (candidate, expected) => {
    expect(nextPath(candidate, ZONE)).toBe(expected);
  });

  it("does not treat a longer first segment as the zone", () => {
    expect(nextPath("/administrator", ZONE)).toBe("/administrator");
  });

  it.each([
    ["/admin//evil.example"],
    ["/admin//evil.example/products"],
    ["/admin/\\evil.example"],
    ["/admin/\n/evil.example"],
  ])("rejects a hidden host behind the zone prefix: %s", (candidate) => {
    expect(nextPath(candidate, ZONE)).toBe("/");
  });

  it("does not loop through the login page of the zone", () => {
    expect(nextPath("/admin/login?reason=forbidden", ZONE)).toBe("/");
  });
});
