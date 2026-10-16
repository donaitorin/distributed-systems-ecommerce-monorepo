import { createAuthRuntime } from "../src";
import { CONFIG, createTestKeys, jsonResponse, tokensBody } from "./support/tokens";

describe("createAuthRuntime", () => {
  it("wires the API, the verifier and the resolver together", async () => {
    const keys = await createTestKeys();
    const access = await keys.sign({ role: "admin" });
    const fetchMock = jest.fn(() => Promise.resolve(jsonResponse(tokensBody(access, "r2"))));
    const runtime = createAuthRuntime(CONFIG, { fetch: fetchMock as unknown as typeof fetch, keySet: keys.keySet });

    const result = await runtime.resolve({ refreshToken: "r1", clientIp: "203.0.113.9" });

    expect(result.session?.role).toBe("admin");
    expect(runtime.config).toBe(CONFIG);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("builds a runtime with the default remote key set", () => {
    expect(typeof createAuthRuntime(CONFIG).verify).toBe("function");
  });
});
