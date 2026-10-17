import { timeoutSignal } from "../src";

describe("timeoutSignal", () => {
  it("aborts by itself once the time has passed", async () => {
    const signal = timeoutSignal(5);

    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(signal.aborted).toBe(true);
    expect((signal.reason as Error).name).toBe("TimeoutError");
  });

  it("is not aborted before the time has passed", () => {
    expect(timeoutSignal(60_000).aborted).toBe(false);
  });

  it("also follows the caller's signal", () => {
    const caller = new AbortController();
    const signal = timeoutSignal(60_000, caller.signal);

    caller.abort();

    expect(signal.aborted).toBe(true);
  });
});
