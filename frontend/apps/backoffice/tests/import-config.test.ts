import { DEFAULT_IMPORT_MAX_BYTES, importMaxBytes } from "../src/server/import-config";

describe("importMaxBytes", () => {
  it("defaults to the backend default of 50 MB", () => {
    expect(DEFAULT_IMPORT_MAX_BYTES).toBe(50 * 1024 * 1024);
    expect(importMaxBytes({})).toBe(52_428_800);
    expect(importMaxBytes({ IMPORT_MAX_BYTES: "  " })).toBe(52_428_800);
  });

  it("reads the same variable as the backend", () => {
    expect(importMaxBytes({ IMPORT_MAX_BYTES: "1048576" })).toBe(1_048_576);
  });

  it.each(["0", "-5", "1.5", "abc", "99999999999999999999"])("refuses %s", (value) => {
    expect(() => importMaxBytes({ IMPORT_MAX_BYTES: value })).toThrow("IMPORT_MAX_BYTES must be a positive integer");
  });
});
