import { retryDelayMs } from "../src";

const POLICY = { attempts: 4, baseDelayMs: 100, maxDelayMs: 500 };

describe("retryDelayMs", () => {
  it("is half the ceiling at least and the whole ceiling at most", () => {
    expect(retryDelayMs(POLICY, 1, () => 0)).toBe(50);
    expect(retryDelayMs(POLICY, 1, () => 1)).toBe(100);
  });

  it("doubles with every attempt up to the maximum", () => {
    expect([1, 2, 3, 4, 5].map((attempt) => retryDelayMs(POLICY, attempt, () => 1))).toEqual([
      100, 200, 400, 500, 500,
    ]);
  });

  it("varies with the random source", () => {
    const delays = new Set([0, 0.25, 0.5, 0.75, 1].map((value) => retryDelayMs(POLICY, 3, () => value)));

    expect(delays.size).toBeGreaterThan(1);
  });
});
