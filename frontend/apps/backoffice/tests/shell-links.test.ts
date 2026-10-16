import { ADMIN_NAVIGATION } from "../src/lib/shell-links";

describe("ADMIN_NAVIGATION", () => {
  it("links to the sections that exist and never to a separate imports page", () => {
    expect(ADMIN_NAVIGATION).toEqual([{ label: "Products", href: "/admin/products" }]);
    expect(ADMIN_NAVIGATION.map((link) => link.label)).not.toContain("Imports");
    expect(ADMIN_NAVIGATION.map((link) => link.href).join()).not.toContain("imports");
  });
});
