import { ADMIN_NAVIGATION } from "../src/lib/shell-links";

describe("ADMIN_NAVIGATION", () => {
  it("links to products, categories, orders and users and never to a separate imports page", () => {
    expect(ADMIN_NAVIGATION).toEqual([
      { label: "Products", href: "/admin/products" },
      { label: "Categories", href: "/admin/categories" },
      { label: "Orders", href: "/admin/orders" },
      { label: "Users", href: "/admin/users" },
    ]);
    expect(ADMIN_NAVIGATION.map((link) => link.label)).not.toContain("Imports");
    expect(ADMIN_NAVIGATION.map((link) => link.href).join()).not.toContain("imports");
  });
});
