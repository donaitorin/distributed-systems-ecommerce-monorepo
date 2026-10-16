/**
 * @jest-environment node
 */
import { uploadProductImage } from "../src/lib/upload-client";
import { json, problem, product } from "./support/api";

describe("uploadProductImage", () => {
  const file = new Blob(["bytes"], { type: "image/png" });

  it("sends the file as multipart form data with the etag to the zone's streaming route", async () => {
    const send = jest.fn(() => Promise.resolve(json(product({ version: 4 }), 200, { etag: '"4"' })));

    const result = await uploadProductImage("RS/001", '"3"', file, send);

    expect(result).toMatchObject({ ok: true, etag: '"4"', product: { version: 4 } });
    const [url, init] = send.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/admin/api/stream/products/RS%2F001/image");
    expect(init.method).toBe("PUT");
    expect(init.headers).toEqual({ "if-match": '"3"' });
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(Blob);
  });

  it("derives the etag from the version when the response has none", async () => {
    const send = jest.fn(() => Promise.resolve(json(product({ version: 8 }))));

    expect(await uploadProductImage("RS-001", '"3"', file, send as unknown as typeof fetch)).toMatchObject({
      etag: '"8"',
    });
  });

  it.each([413, 415, 422, 503])("returns the problem for %s", async (status) => {
    const send = jest.fn(() => Promise.resolve(problem(status, "Problem")));

    expect(await uploadProductImage("RS-001", '"3"', file, send as unknown as typeof fetch)).toMatchObject({
      ok: false,
      status,
    });
  });

  it("returns a network failure when the request cannot be sent", async () => {
    const send = jest.fn(() => Promise.reject(new TypeError("Failed to fetch")));

    expect(await uploadProductImage("RS-001", '"3"', file, send as unknown as typeof fetch)).toMatchObject({
      ok: false,
      status: null,
    });
  });

  it("uses the global fetch by default", async () => {
    const original = global.fetch;
    global.fetch = jest.fn(() => Promise.resolve(json(product())));

    try {
      expect(await uploadProductImage("RS-001", '"3"', file)).toMatchObject({ ok: true });
    } finally {
      global.fetch = original;
    }
  });
});
