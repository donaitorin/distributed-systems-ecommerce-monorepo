import { describeRetry } from "../src";

describe("describeRetry", () => {
  it("describes retry times", () => {
    expect(describeRetry(1)).toBe("1 second");
    expect(describeRetry(42)).toBe("42 seconds");
    expect(describeRetry(90)).toBe("2 minutes");
    expect(describeRetry(600)).toBe("10 minutes");
  });
});
