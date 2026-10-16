import { categoryFormSchema, normalizeCategoryName } from "../src/lib/category-form";

function messageFor(name: string): string | undefined {
  const result = categoryFormSchema.safeParse({ name });
  return result.success ? undefined : result.error.issues[0]?.message;
}

describe("category form", () => {
  it("normalizes whitespace like the backend", () => {
    expect(normalizeCategoryName("  Home   and\toffice \n")).toBe("Home and office");
  });

  it.each(["Electronics", "Café Society", "A", "3D printing", "x".repeat(100)])("accepts %s", (name) => {
    expect(messageFor(name)).toBeUndefined();
  });

  it.each([
    ["", "Name is required"],
    ["   \t ", "Name is required"],
    ["x".repeat(101), "at most 100"],
    ["%%% !!!", "letters or digits"],
    ["日本語", "letters or digits"],
  ])("rejects %j", (name, message) => {
    expect(messageFor(name)).toContain(message);
  });

  it("counts the length after normalizing", () => {
    expect(messageFor(`${"x".repeat(100)}     `)).toBeUndefined();
  });
});
