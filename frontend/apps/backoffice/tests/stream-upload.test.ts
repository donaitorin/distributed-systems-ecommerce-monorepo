/**
 * @jest-environment node
 */
import { streamUpload } from "../src/server/stream-upload";

const CHUNK_BYTES = 64 * 1024;
const MEGABYTE = 1024 * 1024;

function lazyBody(totalBytes: number, onPull: () => void = () => undefined) {
  let produced = 0;
  const stream = new ReadableStream<Uint8Array>(
    {
      pull(controller) {
        onPull();
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

function uploadRequest(body: ReadableStream<Uint8Array> | null, headers: Record<string, string> = {}): Request {
  return new Request("http://backoffice.test/admin/api/stream/products/RS-001/image", {
    method: "PUT",
    body,
    duplex: "half",
    headers: { "content-type": "multipart/form-data; boundary=x", ...headers },
  } as RequestInit & { duplex: "half" });
}

async function drain(body: BodyInit | null | undefined): Promise<number> {
  const reader = (body as ReadableStream<Uint8Array>).getReader();
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      return total;
    }
    total += value.byteLength;
  }
}

const BASE = {
  url: "http://gateway.test/api/v1/products/RS-001/image",
  method: "PUT" as const,
  maxBytes: MEGABYTE,
  headers: { authorization: "Bearer t", "x-forwarded-for": "203.0.113.9" },
  forwardedRequestHeaders: ["content-type", "if-match"],
  timeoutMs: 5000,
};

describe("streamUpload", () => {
  it("rejects by Content-Length without reading a single byte of the body", async () => {
    const pulls = jest.fn();
    const { stream } = lazyBody(200 * MEGABYTE, pulls);
    const send = jest.fn();

    const response = await streamUpload({
      ...BASE,
      request: uploadRequest(stream, { "content-length": String(200 * MEGABYTE) }),
      fetchImplementation: send,
    });

    expect(response.status).toBe(413);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
    expect(await response.json()).toMatchObject({ status: 413, title: "Payload too large" });
    expect(send).not.toHaveBeenCalled();
    expect(pulls).not.toHaveBeenCalled();
  });

  it("rejects an oversized chunked upload after counting a few chunks, not the whole file", async () => {
    const total = 256 * MEGABYTE;
    const { stream, produced } = lazyBody(total);
    const send = jest.fn((_url: string, init: RequestInit) => drain(init.body).then(() => new Response("{}")));

    const response = await streamUpload({
      ...BASE,
      request: uploadRequest(stream),
      fetchImplementation: send as unknown as typeof fetch,
    });

    expect(response.status).toBe(413);
    expect(produced()).toBeLessThanOrEqual(MEGABYTE + 4 * CHUNK_BYTES);
    expect(produced()).toBeLessThan(total / 100);
  });

  it("treats a malformed Content-Length as absent and still counts the bytes", async () => {
    const { stream, produced } = lazyBody(64 * MEGABYTE);
    const send = jest.fn((_url: string, init: RequestInit) => drain(init.body).then(() => new Response("{}")));

    const response = await streamUpload({
      ...BASE,
      request: uploadRequest(stream, { "content-length": "12abc" }),
      fetchImplementation: send as unknown as typeof fetch,
    });

    expect(response.status).toBe(413);
    expect(produced()).toBeLessThanOrEqual(MEGABYTE + 4 * CHUNK_BYTES);
  });

  it("hands the gateway a live stream with duplex half and consumes it as it is produced", async () => {
    const total = 8 * CHUNK_BYTES;
    const { stream, produced } = lazyBody(total);
    let producedAtFirstChunk = -1;
    let bodyType = "";
    let received = 0;
    const send = jest.fn(async (_url: string, init: RequestInit) => {
      bodyType = Object.prototype.toString.call(init.body);
      const reader = (init.body as ReadableStream<Uint8Array>).getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        if (producedAtFirstChunk < 0) {
          producedAtFirstChunk = produced();
        }
        received += value.byteLength;
      }
      return new Response(JSON.stringify({ sku: "RS-001" }), {
        status: 200,
        headers: { "content-type": "application/json", etag: '"4"', "set-cookie": "secret=1", "retry-after": "2" },
      });
    });

    const response = await streamUpload({
      ...BASE,
      request: uploadRequest(stream, { "if-match": '"3"', "content-length": String(total), cookie: "a=b" }),
      fetchImplementation: send as unknown as typeof fetch,
    });

    expect(bodyType).toBe("[object ReadableStream]");
    expect(producedAtFirstChunk).toBeLessThanOrEqual(2 * CHUNK_BYTES);
    expect(received).toBe(total);
    const [url, init] = send.mock.calls[0] as unknown as [string, RequestInit & { duplex: string }];
    expect(url).toBe(BASE.url);
    expect(init.method).toBe("PUT");
    expect(init.duplex).toBe("half");
    const headers = init.headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer t");
    expect(headers.get("x-forwarded-for")).toBe("203.0.113.9");
    expect(headers.get("if-match")).toBe('"3"');
    expect(headers.get("content-type")).toBe("multipart/form-data; boundary=x");
    expect(headers.get("content-length")).toBe(String(total));
    expect(headers.get("cookie")).toBeNull();
    expect(response.status).toBe(200);
    expect(response.headers.get("etag")).toBe('"4"');
    expect(response.headers.get("retry-after")).toBe("2");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ sku: "RS-001" });
  });

  it("passes the gateway's problem responses through", async () => {
    const { stream } = lazyBody(CHUNK_BYTES);
    const send = jest.fn(async (_url: string, init: RequestInit) => {
      await drain(init.body);
      return new Response(JSON.stringify({ title: "Unsupported media type", status: 415 }), {
        status: 415,
        headers: { "content-type": "application/problem+json" },
      });
    });

    const response = await streamUpload({ ...BASE, request: uploadRequest(stream), fetchImplementation: send as unknown as typeof fetch });

    expect(response.status).toBe(415);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
  });

  it("answers 400 without a body", async () => {
    const send = jest.fn();

    const response = await streamUpload({
      ...BASE,
      request: new Request("http://backoffice.test/x", { method: "PUT" }),
      fetchImplementation: send,
    });

    expect(response.status).toBe(400);
    expect(send).not.toHaveBeenCalled();
  });

  it("answers 504 when the gateway takes too long", async () => {
    const { stream } = lazyBody(CHUNK_BYTES);
    const send = jest.fn(() => Promise.reject(new DOMException("timed out", "TimeoutError")));

    const response = await streamUpload({ ...BASE, request: uploadRequest(stream), fetchImplementation: send });

    expect(response.status).toBe(504);
  });

  it("answers 502 when the gateway cannot be reached", async () => {
    const { stream } = lazyBody(CHUNK_BYTES);
    const send = jest.fn(() => Promise.reject(new TypeError("fetch failed")));

    const response = await streamUpload({ ...BASE, request: uploadRequest(stream), fetchImplementation: send });

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ title: "The server could not be reached" });
  });

  it("uses the global fetch by default", async () => {
    const { stream } = lazyBody(CHUNK_BYTES);
    const original = global.fetch;
    global.fetch = jest.fn(async (_url: unknown, init?: RequestInit) => {
      await drain(init?.body);
      return new Response("{}", { status: 200 });
    });

    try {
      const response = await streamUpload({ ...BASE, request: uploadRequest(stream) });
      expect(response.status).toBe(200);
    } finally {
      global.fetch = original;
    }
  });
});
