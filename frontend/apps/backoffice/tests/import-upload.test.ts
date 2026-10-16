/**
 * @jest-environment node
 */
import { POST } from "../src/app/api/stream/imports/route";
import { MULTIPART_OVERHEAD_BYTES, postImport } from "../src/server/import-upload";
import { headerOf, json, mockFetch } from "./support/api";

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

const CHUNK_BYTES = 64 * 1024;
const MEGABYTE = 1024 * 1024;
const DEFAULT_LIMIT = 50 * MEGABYTE;
const ADMIN = {
  ok: true,
  access: { accessToken: "token-1", clientIp: "203.0.113.9", cookies: [{ name: "ecommerce_access", value: "fresh" }] },
};

function lazySource(totalBytes: number) {
  let produced = 0;
  const stream = new ReadableStream<Uint8Array>(
    {
      pull(controller) {
        if (produced >= totalBytes) {
          controller.close();
          return;
        }
        produced += CHUNK_BYTES;
        controller.enqueue(new Uint8Array(CHUNK_BYTES));
      },
    },
    { highWaterMark: 0 },
  );
  return { stream, produced: () => produced };
}

function csvUpload(body: ReadableStream<Uint8Array>, headers: Record<string, string> = {}): Request {
  return new Request("http://backoffice.test/admin/api/stream/imports", {
    method: "POST",
    body,
    duplex: "half",
    headers: { "content-type": "multipart/form-data; boundary=x", ...headers },
  } as RequestInit & { duplex: "half" });
}

async function drain(init: RequestInit | undefined): Promise<number> {
  const reader = (init?.body as ReadableStream<Uint8Array>).getReader();
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      return total;
    }
    total += value.byteLength;
  }
}

const savedLimit = process.env.IMPORT_MAX_BYTES;

beforeEach(() => {
  guardRoute.mockReset();
  guardRoute.mockResolvedValue(ADMIN);
  delete process.env.IMPORT_MAX_BYTES;
});

afterAll(() => {
  if (savedLimit === undefined) {
    delete process.env.IMPORT_MAX_BYTES;
  } else {
    process.env.IMPORT_MAX_BYTES = savedLimit;
  }
});

describe("postImport", () => {
  it("answers the guard's response when the caller is not an admin and never reads the body", async () => {
    guardRoute.mockResolvedValue({ ok: false, response: new Response("no", { status: 401 }) });
    const fetchMock = mockFetch([]);

    const response = await postImport(csvUpload(lazySource(MEGABYTE).stream));

    expect(response.status).toBe(401);
    expect(fetchMock.calls).toHaveLength(0);
    expect(guardRoute).toHaveBeenCalledWith(expect.any(Request), expect.objectContaining({ requiredRole: "admin" }));
  });

  it("streams a 40 MB file to the gateway as it is read, never as a buffer", async () => {
    const source = lazySource(40 * MEGABYTE);
    let producedAtFirstChunk = -1;
    let received = 0;
    const fetchMock = mockFetch([
      {
        method: "POST",
        path: "/api/v1/imports",
        respond: async ({ init }) => {
          const reader = (init.body as ReadableStream<Uint8Array>).getReader();
          for (;;) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }
            if (producedAtFirstChunk < 0) {
              producedAtFirstChunk = source.produced();
            }
            received += value.byteLength;
          }
          return json({ id: "abc", status: "uploaded" }, 202);
        },
      },
    ]);

    const response = await postImport(csvUpload(source.stream, { "content-length": String(40 * MEGABYTE) }));

    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ id: "abc", status: "uploaded" });
    expect(received).toBe(40 * MEGABYTE);
    expect(producedAtFirstChunk).toBeLessThanOrEqual(2 * CHUNK_BYTES);
    const call = fetchMock.calls[0];
    expect(Object.prototype.toString.call(call?.init.body)).toBe("[object ReadableStream]");
    expect((call?.init as RequestInit & { duplex: string }).duplex).toBe("half");
    expect(call?.init.method).toBe("POST");
    expect(headerOf(call?.init ?? {}, "authorization")).toBe("Bearer token-1");
    expect(headerOf(call?.init ?? {}, "x-forwarded-for")).toBe("203.0.113.9");
    expect(headerOf(call?.init ?? {}, "content-type")).toBe("multipart/form-data; boundary=x");
    expect(headerOf(call?.init ?? {}, "content-length")).toBe(String(40 * MEGABYTE));
    expect(response.headers.get("set-cookie")).toBe("ecommerce_access=fresh");
  });

  it("passes a 200 for a file that was uploaded before", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/imports", respond: async ({ init }) => { await drain(init); return json({ id: "abc" }, 200); } }]);

    const response = await postImport(csvUpload(lazySource(CHUNK_BYTES).stream));

    expect(response.status).toBe(200);
  });

  it("refuses by Content-Length, past the 50 MB limit, before reading a byte", async () => {
    const pulls = jest.fn();
    const stream = new ReadableStream<Uint8Array>({ pull: pulls }, { highWaterMark: 0 });
    const fetchMock = mockFetch([]);

    const response = await postImport(
      csvUpload(stream, { "content-length": String(DEFAULT_LIMIT + MULTIPART_OVERHEAD_BYTES + 1) }),
    );

    expect(response.status).toBe(413);
    expect(await response.json()).toMatchObject({ title: "Payload too large", detail: expect.stringContaining("50 MB") as string });
    expect(fetchMock.calls).toHaveLength(0);
    expect(pulls).not.toHaveBeenCalled();
  });

  it("accepts a file at the limit by Content-Length", async () => {
    mockFetch([{ method: "POST", path: "/api/v1/imports", respond: async ({ init }) => { await drain(init); return json({ id: "abc" }, 202); } }]);

    const response = await postImport(
      csvUpload(lazySource(MEGABYTE).stream, { "content-length": String(DEFAULT_LIMIT + MULTIPART_OVERHEAD_BYTES) }),
    );

    expect(response.status).toBe(202);
  });

  it("cuts off a chunked 512 MB source near the 50 MB limit, so memory never holds the file", async () => {
    const total = 512 * MEGABYTE;
    const source = lazySource(total);
    mockFetch([{ method: "POST", path: "/api/v1/imports", respond: async ({ init }) => { await drain(init); return json({}, 202); } }]);

    const response = await postImport(csvUpload(source.stream));

    expect(response.status).toBe(413);
    expect(source.produced()).toBeLessThanOrEqual(DEFAULT_LIMIT + MULTIPART_OVERHEAD_BYTES + 4 * CHUNK_BYTES);
    expect(source.produced()).toBeLessThan(total / 5);
  });

  it("uses the same IMPORT_MAX_BYTES as the backend", async () => {
    process.env.IMPORT_MAX_BYTES = String(MEGABYTE);
    const source = lazySource(256 * MEGABYTE);
    mockFetch([{ method: "POST", path: "/api/v1/imports", respond: async ({ init }) => { await drain(init); return json({}, 202); } }]);

    const response = await postImport(csvUpload(source.stream));

    expect(response.status).toBe(413);
    expect(source.produced()).toBeLessThanOrEqual(MEGABYTE + MULTIPART_OVERHEAD_BYTES + 4 * CHUNK_BYTES);
    expect(await (await postImport(csvUpload(lazySource(0).stream, { "content-length": String(2 * MEGABYTE) }))).json()).toMatchObject({
      status: 413,
    });
  });

  it("passes the backend's problems through", async () => {
    mockFetch([
      {
        method: "POST",
        path: "/api/v1/imports",
        respond: async ({ init }) => {
          await drain(init);
          return new Response(JSON.stringify({ title: "Unsupported media type", status: 415 }), {
            status: 415,
            headers: { "content-type": "application/problem+json" },
          });
        },
      },
    ]);

    const response = await postImport(csvUpload(lazySource(CHUNK_BYTES).stream));

    expect(response.status).toBe(415);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
  });
});

describe("import upload route", () => {
  it("is the POST handler of /api/stream/imports", async () => {
    guardRoute.mockResolvedValue({ ok: false, response: new Response("no", { status: 403 }) });

    const response = await POST(csvUpload(lazySource(CHUNK_BYTES).stream));

    expect(response.status).toBe(403);
  });
});
