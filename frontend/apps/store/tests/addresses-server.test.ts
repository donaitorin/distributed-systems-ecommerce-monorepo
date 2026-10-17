/**
 * @jest-environment node
 */
import type { Failure } from "@ecommerce/web-core";
import { addAddress, loadAddresses, removeAddress } from "../src/server/addresses";
import { EMPTY_ADDRESS } from "../src/lib/addresses";
import { json, mockFetch, problem } from "./support/api";
import { address, ADDRESS_ID } from "./support/addresses";

jest.mock("@ecommerce/auth/next", () => ({
  authRuntime: () => ({ config: { apiBaseUrl: "http://gateway.test" } }),
  authorizationHeaders: () => ({ authorization: "Bearer t" }),
}));
jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

const LIST = { method: "GET", path: "/api/v1/accounts/me/addresses" };
const CREATE = { method: "POST", path: "/api/v1/accounts/me/addresses" };
const DELETE = { method: "DELETE", path: `/api/v1/accounts/me/addresses/${ADDRESS_ID}` };
const VALUES = { ...EMPTY_ADDRESS, recipient_name: "Ada", line1: "1 St", city: "London", postal_code: "N1", country: "gb" };

describe("loadAddresses", () => {
  it("lists the saved addresses", async () => {
    mockFetch([{ ...LIST, respond: () => json({ items: [address()] }) }]);

    expect(await loadAddresses("/account")).toEqual([address()]);
  });

  it("sends an expired session to the login page and back to where it was", async () => {
    mockFetch([{ ...LIST, respond: () => problem(401, "Unauthorized") }]);

    await expect(loadAddresses("/checkout")).rejects.toThrow("NEXT_REDIRECT /login?next=%2Fcheckout&reason=expired");
  });

  it("returns a failure when accounts is unreachable", async () => {
    mockFetch([{ ...LIST, respond: () => problem(503, "Down") }]);

    expect(await loadAddresses("/account")).toMatchObject({ ok: false, status: 503 });
  });
});

describe("addAddress", () => {
  it("validates before calling the API", async () => {
    const api = mockFetch([]);

    const result = await addAddress({ ...VALUES, city: "", country: "GBR" }, "/account");

    expect(result).toMatchObject({ ok: false, status: 422 });
    expect(Object.keys((result as Failure).fieldErrors).sort()).toEqual(["city", "country"]);
    expect(api.calls).toHaveLength(0);
  });

  it("posts the normalized body and returns the saved address", async () => {
    const api = mockFetch([{ ...CREATE, respond: () => json(address(), 201) }]);

    expect(await addAddress(VALUES, "/account")).toEqual({ ok: true, address: address() });
    expect(JSON.parse(api.calls[0]?.init.body as string)).toMatchObject({ country: "GB", line2: null, phone: null });
  });

  it("words the field errors of the API", async () => {
    mockFetch([
      {
        ...CREATE,
        respond: () =>
          problem(422, "Validation failed", { errors: [{ location: "body.phone", message: "phone must start with +", type: "value_error" }] }),
      },
    ]);

    const result = (await addAddress(VALUES, "/account")) as Failure;

    expect(result.status).toBe(422);
    expect(result.fieldErrors.phone).toContain("country code");
  });

  it("reports the limit of addresses as a conflict", async () => {
    mockFetch([{ ...CREATE, respond: () => problem(409, "Conflict") }]);

    expect(await addAddress(VALUES, "/account")).toMatchObject({ ok: false, status: 409 });
  });

  it("returns to the page where the session expired", async () => {
    mockFetch([{ ...CREATE, respond: () => problem(401, "Unauthorized") }]);

    await expect(addAddress(VALUES, "/checkout")).rejects.toThrow("reason=expired");
  });
});

describe("removeAddress", () => {
  it("deletes the address", async () => {
    mockFetch([{ ...DELETE, respond: () => new Response(null, { status: 204 }) }]);

    expect(await removeAddress(ADDRESS_ID, "/account")).toEqual({ ok: true });
  });

  it("treats an address that is already gone as deleted", async () => {
    mockFetch([{ ...DELETE, respond: () => problem(404, "Not found") }]);

    expect(await removeAddress(ADDRESS_ID, "/account")).toEqual({ ok: true });
  });

  it("does not call the API for an id that is not a UUID, and says it was not found", async () => {
    const api = mockFetch([]);

    expect(await removeAddress("../me", "/account")).toMatchObject({ ok: false, status: 404 });
    expect(api.calls).toHaveLength(0);
  });

  it("returns the failure of the API", async () => {
    mockFetch([{ ...DELETE, respond: () => problem(503, "Down") }]);

    expect(await removeAddress(ADDRESS_ID, "/account")).toMatchObject({ ok: false, status: 503 });
  });
});
