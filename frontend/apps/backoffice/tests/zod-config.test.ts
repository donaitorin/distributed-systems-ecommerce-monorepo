import { z } from "zod";
import "../src/lib/product-form";
import "../src/lib/category-form";

describe("zod configuration", () => {
  it("is applied by the form schemas of the app", () => {
    expect(z.config().jitless).toBe(true);
  });
});
