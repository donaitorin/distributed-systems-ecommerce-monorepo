/**
 * @jest-environment node
 */
import { adminNextPath } from "../src/lib/next-path";

describe("adminNextPath", () => {
  it.each([
    ["/products", "/products"],
    ["/products?q=shoes&sort=newest", "/products?q=shoes&sort=newest"],
    ["/products/RS-001", "/products/RS-001"],
    ["/", "/"],
  ])("keeps the internal path %s", (candidate, expected) => {
    expect(adminNextPath(candidate)).toBe(expected);
  });

  it.each([
    ["/admin", "/"],
    ["/admin/", "/"],
    ["/admin/products", "/products"],
    ["/admin/products?q=a", "/products?q=a"],
    ["/admin?x=1", "/?x=1"],
  ])("removes the zone prefix, which the router adds back: %s", (candidate, expected) => {
    expect(adminNextPath(candidate)).toBe(expected);
  });

  it("does not treat a longer first segment as the zone", () => {
    expect(adminNextPath("/administrator")).toBe("/administrator");
  });

  it.each([
    ["an absolute URL", "https://evil.example/phish"],
    ["a protocol relative URL", "//evil.example"],
    ["a protocol relative URL after the zone prefix", "/admin//evil.example"],
    ["a protocol relative URL with the zone prefix doubled", "/admin//evil.example/products"],
    ["backslashes", "/\\evil.example"],
    ["backslashes after the zone prefix", "/admin/\\evil.example"],
    ["a javascript URL", "javascript:alert(1)"],
    ["a data URL", "data:text/html,<script>alert(1)</script>"],
    ["a scheme without slashes", "http:evil.example"],
    ["a relative path", "products"],
    ["a tab inside the path", "/\t/evil.example"],
    ["a newline inside the path", "/admin/\n/evil.example"],
    ["an empty value", ""],
  ])("falls back to the home page for %s", (_label, candidate) => {
    expect(adminNextPath(candidate)).toBe("/");
  });

  it.each([null, undefined])("falls back to the home page for %s", (candidate) => {
    expect(adminNextPath(candidate)).toBe("/");
  });

  it.each(["/login", "/login?next=%2Fproducts", "/login/", "/admin/login", "/admin/login?reason=forbidden"])(
    "never sends the administrator back to the login page: %s",
    (candidate) => {
      expect(adminNextPath(candidate)).toBe("/");
    },
  );
});
