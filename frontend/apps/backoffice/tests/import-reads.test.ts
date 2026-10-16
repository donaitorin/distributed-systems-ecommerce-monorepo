/**
 * @jest-environment node
 */
import { GET as getImport } from "../src/app/api/imports/[id]/route";
import { GET as getProblems } from "../src/app/api/imports/[id]/problems/route";
import { GET as getCsv } from "../src/app/api/imports/[id]/problems.csv/route";
import { confirmImportAction, revalidateImportAction } from "../src/app/products/import/actions";
import { confirmImport, revalidateImport } from "../src/server/import-actions";
import { downloadProblemsCsv, failureResponse, isImportId, readImport, readProblems } from "../src/server/import-reads";
import { headerOf, importView, json, mockFetch, problem } from "./support/api";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => Promise.resolve({ authorization: "Bearer t", "x-forwarded-for": "203.0.113.9" }),
}));

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

const ID = "9f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f";
const context = (id: string) => ({ params: Promise.resolve({ id }) });
const request = (query = "") => new Request(`http://backoffice.test/admin/api/imports/${ID}/problems${query}`);

describe("isImportId", () => {
  it("accepts UUIDs only", () => {
    expect(isImportId(ID)).toBe(true);
    expect(isImportId(ID.toUpperCase())).toBe(true);
    for (const value of ["", "abc", `${ID}x`, "../../etc/passwd", `${ID}/confirm`]) {
      expect(isImportId(value)).toBe(false);
    }
  });
});

describe("failureResponse", () => {
  it("is problem+json with the status, the detail and the retry time", async () => {
    const response = failureResponse({ ok: false, status: 503, title: "Down", detail: "later", fieldErrors: {}, retryAfterSeconds: 7 });

    expect(response.status).toBe(503);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
    expect(response.headers.get("retry-after")).toBe("7");
    expect(await response.json()).toMatchObject({ title: "Down", detail: "later", status: 503 });
  });

  it("answers 502 when there is no status", () => {
    expect(failureResponse({ ok: false, status: null, title: "Unreachable", fieldErrors: {} }).status).toBe(502);
  });
});

describe("reading an import", () => {
  it("returns the import as JSON that is never cached", async () => {
    const api = mockFetch([{ method: "GET", path: `/api/v1/imports/${ID}`, respond: () => json(importView()) }]);

    const response = await getImport(new Request("http://x"), context(ID));

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toMatchObject({ status: "validated" });
    expect(headerOf(api.calls[0]?.init ?? {}, "authorization")).toBe("Bearer t");
  });

  it("does not call the API for an id that is not a UUID", async () => {
    const api = mockFetch([]);

    const response = await readImport("../secret");

    expect(response.status).toBe(404);
    expect(api.calls).toHaveLength(0);
  });

  it.each([401, 403, 404])("passes %s on as a problem, not as a redirect", async (status) => {
    mockFetch([{ method: "GET", path: `/api/v1/imports/${ID}`, respond: () => problem(status, "Problem") }]);

    const response = await readImport(ID);

    expect(response.status).toBe(status);
    expect(response.headers.get("content-type")).toBe("application/problem+json");
  });

  it("answers 502 when the API cannot be reached", async () => {
    mockFetch([]);

    expect((await readImport(ID)).status).toBe(502);
  });
});

describe("reading problems", () => {
  const page = { items: [{ severity: "error", row: 7, column: "price", value: "free", code: "x", reason: "bad" }], next_cursor: "n" };

  it("forwards the severity, the cursor and the page size", async () => {
    const api = mockFetch([{ method: "GET", path: `/api/v1/imports/${ID}/problems`, respond: () => json(page) }]);

    const response = await getProblems(request("?severity=warning&cursor=abc&limit=50"), context(ID));

    expect(await response.json()).toMatchObject({ next_cursor: "n" });
    expect(Object.fromEntries(api.calls[0]?.url.searchParams ?? [])).toEqual({ severity: "warning", cursor: "abc", limit: "50" });
  });

  it("ignores values the API would not accept", async () => {
    const api = mockFetch([{ method: "GET", path: `/api/v1/imports/${ID}/problems`, respond: () => json(page) }]);

    await readProblems(ID, { severity: "fatal", cursor: null, limit: "many" });

    expect([...(api.calls[0]?.url.searchParams ?? [])]).toEqual([]);
  });

  it("rejects an invalid id and passes failures on", async () => {
    expect((await readProblems("nope", { severity: null, cursor: null, limit: null })).status).toBe(404);
    mockFetch([{ method: "GET", path: `/api/v1/imports/${ID}/problems`, respond: () => problem(422, "Invalid cursor") }]);

    expect((await readProblems(ID, { severity: null, cursor: "bad", limit: null })).status).toBe(422);
  });
});

describe("downloading problems.csv", () => {
  it("streams the CSV through with its name and never caches it", async () => {
    const api = mockFetch([
      {
        method: "GET",
        path: `/api/v1/imports/${ID}/problems.csv`,
        respond: () =>
          new Response("severity,row\r\nerror,7\r\n", {
            headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": 'attachment; filename="p.csv"' },
          }),
      },
    ]);

    const response = await getCsv(new Request("http://x"), context(ID));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("text/csv; charset=utf-8");
    expect(response.headers.get("content-disposition")).toBe('attachment; filename="p.csv"');
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.text()).toBe("severity,row\r\nerror,7\r\n");
    expect(headerOf(api.calls[0]?.init ?? {}, "authorization")).toBe("Bearer t");
  });

  it("falls back to a file name and a CSV type when the API sends none", async () => {
    mockFetch([{ method: "GET", path: `/api/v1/imports/${ID}/problems.csv`, respond: () => new Response(new Uint8Array([97])) }]);

    const response = await downloadProblemsCsv(ID);

    expect(response.headers.get("content-disposition")).toContain(`import-${ID}-problems.csv`);
    expect(response.headers.get("content-type")).toContain("text/csv");
  });

  it("passes failures on, rejects bad ids and survives an unreachable API", async () => {
    mockFetch([{ method: "GET", path: `/api/v1/imports/${ID}/problems.csv`, respond: () => problem(404, "Not found") }]);
    expect((await downloadProblemsCsv(ID)).status).toBe(404);
    expect((await downloadProblemsCsv("x")).status).toBe(404);
    mockFetch([]);
    expect((await downloadProblemsCsv(ID)).status).toBe(502);
  });
});

describe("confirming and validating again", () => {
  it("confirm posts to the API and returns the import", async () => {
    mockFetch([{ method: "POST", path: `/api/v1/imports/${ID}/confirm`, respond: () => json(importView({ status: "queued" }), 202) }]);

    expect(await confirmImport(ID)).toMatchObject({ ok: true, import: { status: "queued" } });
    expect(await confirmImportAction(ID)).toMatchObject({ ok: true });
  });

  it("revalidate posts to the API and returns the import", async () => {
    mockFetch([{ method: "POST", path: `/api/v1/imports/${ID}/revalidate`, respond: () => json(importView({ status: "uploaded" }, null), 202) }]);

    expect(await revalidateImport(ID)).toMatchObject({ ok: true, import: { status: "uploaded" } });
    expect(await revalidateImportAction(ID)).toMatchObject({ ok: true });
  });

  it("returns a 409 as a failure and sends an expired session to the login page", async () => {
    mockFetch([{ method: "POST", path: `/api/v1/imports/${ID}/confirm`, respond: () => problem(409, "Import cannot be confirmed", { detail: "not validated" }) }]);
    expect(await confirmImport(ID)).toMatchObject({ ok: false, status: 409, detail: "not validated" });

    mockFetch([{ method: "POST", path: `/api/v1/imports/${ID}/revalidate`, respond: () => problem(401, "Unauthorized") }]);
    await expect(revalidateImport(ID)).rejects.toThrow("NEXT_REDIRECT /login?reason=expired");
  });
});
