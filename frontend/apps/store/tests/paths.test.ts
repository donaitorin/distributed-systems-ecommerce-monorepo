/**
 * @jest-environment node
 */
import { navigationFor } from "../src/lib/shell-links";
import { authPageHref, categoryHref, isProtectedPath, orderHref, productHref, storeNextPath } from "../src/lib/paths";

describe("storeNextPath", () => {
  it.each([
    ["/account", "/account"],
    ["/products?q=shoes&sort=newest", "/products?q=shoes&sort=newest"],
    ["/products/RS-001", "/products/RS-001"],
    ["/", "/"],
  ])("keeps the internal path %s", (candidate, expected) => {
    expect(storeNextPath(candidate)).toBe(expected);
  });

  it.each([
    ["an absolute URL", "https://evil.example/phish"],
    ["a protocol relative URL", "//evil.example"],
    ["backslashes", "/\\evil.example"],
    ["a javascript URL", "javascript:alert(1)"],
    ["a scheme without slashes", "http:evil.example"],
    ["a relative path", "account"],
    ["a tab inside the path", "/\t/evil.example"],
    ["a newline inside the path", "/\n/evil.example"],
    ["an empty value", ""],
  ])("sends the visitor to the products page instead of %s", (_label, candidate) => {
    expect(storeNextPath(candidate)).toBe("/products");
  });

  it.each([null, undefined])("falls back for %s", (candidate) => {
    expect(storeNextPath(candidate)).toBe("/products");
  });

  it.each(["/login", "/login?next=%2Faccount", "/register", "/register/", "/register?next=%2Faccount"])(
    "never loops through %s",
    (candidate) => {
      expect(storeNextPath(candidate)).toBe("/products");
    },
  );
});

describe("links", () => {
  it("builds product and category links with encoded values", () => {
    expect(productHref("A/B C")).toBe("/products/A%2FB%20C");
    expect(orderHref("6f1c2f64-3f0e")).toBe("/orders/6f1c2f64-3f0e");
    expect(orderHref("a/b")).toBe("/orders/a%2Fb");
    expect(categoryHref("home & garden")).toBe("/products?category=home%20%26%20garden");
  });

  it("keeps the next page in the links between the sign in and sign up pages, unless it is the default", () => {
    expect(authPageHref("/login", "/products")).toBe("/login");
    expect(authPageHref("/register", "/account")).toBe("/register?next=%2Faccount");
    expect(authPageHref("/login", "/products?q=a&b=c")).toBe("/login?next=%2Fproducts%3Fq%3Da%26b%3Dc");
  });

  it("protects the account, checkout and orders pages only", () => {
    expect(isProtectedPath("/account")).toBe(true);
    expect(isProtectedPath("/orders/1")).toBe(true);
    expect(isProtectedPath("/checkout")).toBe(true);
    expect(isProtectedPath("/api/orders/1")).toBe(true);
    expect(isProtectedPath("/api/orderly")).toBe(false);
    expect(isProtectedPath("/accounts")).toBe(false);
    expect(isProtectedPath("/products")).toBe(false);
  });
});

describe("navigationFor", () => {
  it("offers Sign in when signed out", () => {
    expect(navigationFor(false)).toEqual([
      { label: "Products", href: "/products" },
      { label: "Sign in", href: "/login" },
    ]);
  });

  it("offers Orders and Account instead of Sign in when signed in", () => {
    expect(navigationFor(true)).toEqual([
      { label: "Products", href: "/products" },
      { label: "Orders", href: "/orders" },
      { label: "Account", href: "/account" },
    ]);
  });
});
