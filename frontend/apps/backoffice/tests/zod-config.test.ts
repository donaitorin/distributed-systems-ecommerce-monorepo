import { z } from "zod";
import "../src/lib/product-form";
import "../src/lib/product-search";

describe("zod configuration", () => {
  it("runs without the JIT compiler, which probes eval and trips the strict CSP", () => {
    expect(z.config().jitless).toBe(true);
  });
});
