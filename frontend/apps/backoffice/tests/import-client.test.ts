/**
 * @jest-environment node
 */
import {
  fetchImport,
  fetchProblems,
  ImportRequestError,
  importUrl,
  problemsCsvUrl,
  READ_TIMEOUT_MS,
  unwrap,
  UPLOAD_TIMEOUT_MS,
  uploadImportFile,
} from "../src/lib/import-client";
import { importView, json, problem } from "./support/api";

const ID = "9f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f";

function sender(response: Response | Promise<Response>) {
  return jest.fn(() => Promise.resolve(response)) as unknown as typeof fetch & jest.Mock;
}

describe("import client timeouts", () => {
  it("gives reads a short timeout and the upload a long one", async () => {
    const timeout = jest.spyOn(AbortSignal, "timeout");

    await fetchImport(ID, sender(json(importView())));
    await fetchProblems(ID, { severity: null, cursor: null }, sender(json({ items: [], next_cursor: null })));
    await uploadImportFile(new Blob(["a"]), sender(json(importView(), 202)));

    expect(timeout.mock.calls.map(([milliseconds]) => milliseconds)).toEqual([
      READ_TIMEOUT_MS,
      READ_TIMEOUT_MS,
      UPLOAD_TIMEOUT_MS,
    ]);
    expect(READ_TIMEOUT_MS).toBeLessThan(UPLOAD_TIMEOUT_MS);
    timeout.mockRestore();
  });

  it("ends as an unreachable server when the timeout elapses", async () => {
    const hung = jest.fn((_url: string, init: RequestInit) =>
      init.signal?.aborted
        ? Promise.reject(new DOMException("timed out", "TimeoutError"))
        : Promise.resolve(json(importView())),
    ) as unknown as typeof fetch;
    const timeout = jest.spyOn(AbortSignal, "timeout").mockImplementation(() => AbortSignal.abort());

    const result = await fetchImport(ID, hung);

    expect(result).toMatchObject({ ok: false, status: null, title: "The server could not be reached" });
    timeout.mockRestore();
  });
});

describe("import client", () => {
  it("builds the zone's own URLs", () => {
    expect(importUrl(ID)).toBe(`/admin/api/imports/${ID}`);
    expect(problemsCsvUrl(ID)).toBe(`/admin/api/imports/${ID}/problems.csv`);
  });

  it("uploads multipart data to the streaming route and tells a new import from an existing one", async () => {
    const send = sender(json(importView({ status: "uploaded" }), 202));

    const created = await uploadImportFile(new Blob(["a"]), send);

    expect(created).toMatchObject({ ok: true, existing: false, import: { status: "uploaded" } });
    const [url, init] = send.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/admin/api/stream/imports");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.redirect).toBe("manual");
    expect((init.body as FormData).get("file")).toBeInstanceOf(Blob);
    expect(await uploadImportFile(new Blob(["a"]), sender(json(importView(), 200)))).toMatchObject({ existing: true });
  });

  it.each([413, 415, 422, 503])("returns the problem for an upload answered %s", async (status) => {
    expect(await uploadImportFile(new Blob(["a"]), sender(problem(status, "Problem")))).toMatchObject({ ok: false, status });
  });

  it("reports an unreachable server and an expired session", async () => {
    const down = jest.fn(() => Promise.reject(new TypeError("offline"))) as unknown as typeof fetch;
    expect(await uploadImportFile(new Blob(["a"]), down)).toMatchObject({ ok: false, status: null });

    const redirected = { type: "opaqueredirect", ok: false, status: 0 } as unknown as Response;
    expect(await fetchImport(ID, sender(redirected))).toMatchObject({ ok: false, status: 401 });
  });

  it("fetches an import", async () => {
    const send = sender(json(importView()));

    expect(await fetchImport(ID, send)).toMatchObject({ ok: true, import: { status: "validated" } });
    expect((send.mock.calls[0] as unknown as [string])[0]).toBe(importUrl(ID));
  });

  it("returns a 404 as a failure", async () => {
    expect(await fetchImport(ID, sender(problem(404, "Not found")))).toMatchObject({ ok: false, status: 404 });
  });

  it("fetches problems with the severity, the cursor and a page size", async () => {
    const send = sender(json({ items: [], next_cursor: "n" }));

    expect(await fetchProblems(ID, { severity: "error", cursor: "abc" }, send)).toMatchObject({
      ok: true,
      page: { next_cursor: "n" },
    });
    expect((send.mock.calls[0] as unknown as [string])[0]).toBe(`${importUrl(ID)}/problems?limit=50&severity=error&cursor=abc`);

    const plain = sender(json({ items: [], next_cursor: null }));
    await fetchProblems(ID, { severity: null, cursor: null, limit: 25 }, plain);
    expect((plain.mock.calls[0] as unknown as [string])[0]).toBe(`${importUrl(ID)}/problems?limit=25`);
  });

  it("returns failed problems requests", async () => {
    expect(await fetchProblems(ID, { severity: null, cursor: null }, sender(problem(500, "Boom")))).toMatchObject({
      ok: false,
      status: 500,
    });
  });

  it("unwrap returns a success and throws the failure otherwise", () => {
    expect(unwrap({ ok: true, value: 1 })).toEqual({ ok: true, value: 1 });
    expect(() => unwrap({ ok: false, status: 404, title: "Gone", fieldErrors: {} })).toThrow(ImportRequestError);
    try {
      unwrap({ ok: false, status: 503, title: "Down", fieldErrors: {} });
    } catch (error) {
      expect((error as ImportRequestError).failure.status).toBe(503);
    }
  });
});
