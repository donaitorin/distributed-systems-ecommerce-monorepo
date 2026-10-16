/**
 * @jest-environment node
 */
import { PUT } from "../src/app/api/stream/products/[sku]/image/route";
import { putProductImage } from "../src/server/image-upload";
import { json, headerOf, mockFetch } from "./support/api";

const guardRoute = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  guardRoute: (...args: unknown[]) => guardRoute(...args) as unknown,
  applyCookies: (response: Response, specs: { name: string; value: string }[]) => {
    for (const spec of specs) {
      response.headers.append("set-cookie", `${spec.name}=${spec.value}`);
    }
    return response;
  },
}));

function upload(headers: Record<string, string> = {}): Request {
  return new Request("http://backoffice.test/admin/api/stream/products/RS-001/image", {
    method: "PUT",
    body: new Blob(["image-bytes"]),
    headers: { "content-type": "multipart/form-data; boundary=x", "if-match": '"3"', ...headers },
  });
}

beforeEach(() => {
  guardRoute.mockReset();
});

describe("putProductImage", () => {
  it("answers the guard's response when the caller is not an admin", async () => {
    guardRoute.mockResolvedValue({ ok: false, response: new Response("no", { status: 401 }) });
    const fetchMock = mockFetch([]);

    const response = await putProductImage(upload(), "RS-001");

    expect(response.status).toBe(401);
    expect(fetchMock.calls).toHaveLength(0);
    expect(guardRoute).toHaveBeenCalledWith(expect.any(Request), expect.objectContaining({ requiredRole: "admin" }));
  });

  it("streams the file to the gateway as the admin and returns the refreshed cookies", async () => {
    guardRoute.mockResolvedValue({
      ok: true,
      access: {
        accessToken: "token-1",
        clientIp: "203.0.113.9",
        cookies: [{ name: "ecommerce_access", value: "fresh" }],
      },
    });
    const fetchMock = mockFetch([
      {
        method: "PUT",
        path: "/api/v1/products/RS%2F-001/image",
        respond: () => json({ sku: "RS/-001" }, 200, { etag: '"4"' }),
      },
    ]);

    const response = await putProductImage(upload(), "RS/-001");

    expect(response.status).toBe(200);
    expect(response.headers.get("etag")).toBe('"4"');
    expect(response.headers.get("set-cookie")).toBe("ecommerce_access=fresh");
    const call = fetchMock.calls[0];
    expect(call?.init.method).toBe("PUT");
    expect(headerOf(call?.init ?? {}, "authorization")).toBe("Bearer token-1");
    expect(headerOf(call?.init ?? {}, "x-forwarded-for")).toBe("203.0.113.9");
    expect(headerOf(call?.init ?? {}, "if-match")).toBe('"3"');
  });

  it("refuses files over the image limit before contacting the gateway", async () => {
    guardRoute.mockResolvedValue({ ok: true, access: { accessToken: "t", clientIp: undefined, cookies: [] } });
    const fetchMock = mockFetch([]);

    const response = await putProductImage(upload({ "content-length": String(6 * 1024 * 1024) }), "RS-001");

    expect(response.status).toBe(413);
    expect(fetchMock.calls).toHaveLength(0);
  });
});

describe("image route", () => {
  it("reads the SKU from the route parameters", async () => {
    guardRoute.mockResolvedValue({ ok: false, response: new Response("no", { status: 403 }) });

    const response = await PUT(upload(), { params: Promise.resolve({ sku: "RS-001" }) });

    expect(response.status).toBe(403);
  });
});
