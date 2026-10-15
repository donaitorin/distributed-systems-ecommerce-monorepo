import { cn } from "./cn";

describe("cn", () => {
  it("joins truthy class names and skips falsy ones", () => {
    expect(cn("a", false, null, undefined, "b")).toBe("a b");
  });

  it("lets the last conflicting Tailwind utility win", () => {
    expect(cn("px-4 text-sm", "px-8")).toBe("text-sm px-8");
  });

  it("keeps a text size and a text color together", () => {
    expect(cn("text-sm", "text-danger")).toBe("text-sm text-danger");
  });

  it("supports conditional objects", () => {
    expect(cn({ "font-bold": true, italic: false })).toBe("font-bold");
  });
});
