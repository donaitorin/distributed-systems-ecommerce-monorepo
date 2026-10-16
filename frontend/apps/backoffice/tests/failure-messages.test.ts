/**
 * @jest-environment node
 */
import { ApiError, ApiNetworkError } from "@ecommerce/api-client";
import { failureFromError, failureFromProblem, failureFromResponse, isSessionFailure } from "../src/lib/failure";
import { LOGIN_REASON_MESSAGES, rateLimitedMessage, validateCredentials } from "../src/lib/login-form";
import {
  importActionFailureMessage,
  importLoadFailureMessage,
  importUploadFailureMessage,
  categoryFailureMessage,
  roleChangeFailureMessage,
  deleteFailureMessage,
  describeRetry,
  imageFailureMessage,
  saveFailureMessage,
  validateImageFile,
} from "../src/lib/messages";
import { problem } from "./support/api";

describe("failures", () => {
  it("reads body and query field errors and keeps the first per field", () => {
    const failure = failureFromProblem(
      {
        type: "about:blank",
        title: "Validation failed",
        status: 422,
        detail: "bad",
        errors: [
          { location: "body.price", message: "first", type: "a" },
          { location: "body.price", message: "second", type: "a" },
          { location: "query.min_price", message: "q", type: "a" },
          { location: "header.if-match", message: "no", type: "a" },
        ],
      },
      7,
    );

    expect(failure).toEqual({
      ok: false,
      status: 422,
      title: "Validation failed",
      detail: "bad",
      fieldErrors: { price: "first", min_price: "q" },
      retryAfterSeconds: 7,
    });
  });

  it("converts API and network errors and rethrows the rest", () => {
    const response = problem(503, "Down", {}, { "retry-after": "3" });
    const apiError = new ApiError({ type: "about:blank", title: "Down", status: 503 }, response);

    expect(failureFromError(apiError)).toMatchObject({ status: 503, retryAfterSeconds: 3 });
    expect(failureFromError(new ApiNetworkError(new Error("x")))).toMatchObject({ status: null });
    expect(() => failureFromError(new Error("bug"))).toThrow("bug");
  });

  it("reads a failed response, with or without Retry-After", async () => {
    expect(await failureFromResponse(problem(413, "Too large"))).toMatchObject({ status: 413 });
    expect(await failureFromResponse(problem(503, "Down", {}, { "retry-after": "9" }))).toMatchObject({
      retryAfterSeconds: 9,
    });
    expect(await failureFromResponse(new Response("Bad gateway", { status: 502 }))).toMatchObject({ status: 502 });
  });

  it("recognises session failures", () => {
    expect(isSessionFailure({ ok: false, status: 401, title: "", fieldErrors: {} })).toBe(true);
    expect(isSessionFailure({ ok: false, status: 403, title: "", fieldErrors: {} })).toBe(true);
    expect(isSessionFailure({ ok: false, status: 404, title: "", fieldErrors: {} })).toBe(false);
  });
});


describe("messages", () => {
  const failure = (status: number | null, extra: object = {}) => ({
    ok: false as const,
    status,
    title: "Title",
    fieldErrors: {},
    ...extra,
  });

  it("describes retry times", () => {
    expect(describeRetry(1)).toBe("1 second");
    expect(describeRetry(42)).toBe("42 seconds");
    expect(describeRetry(90)).toBe("2 minutes");
    expect(describeRetry(600)).toBe("10 minutes");
  });

  it.each([
    [404, "no longer exists"],
    [409, "already in use"],
    [422, "Some fields need attention"],
    [428, "out of date"],
    [429, "Too many requests"],
    [500, "not available"],
    [null, "not available"],
    [400, "Detail"],
  ])("explains save failure %s", (status, text) => {
    expect(saveFailureMessage(failure(status, { detail: "Detail" }))).toContain(text);
  });

  it("includes the retry time when it is known", () => {
    expect(saveFailureMessage(failure(429, { retryAfterSeconds: 30 }))).toContain("Try again in 30 seconds");
    expect(saveFailureMessage(failure(503, { retryAfterSeconds: 2 }))).toContain("Try again in 2 seconds");
  });

  it("falls back to the title without a detail", () => {
    expect(saveFailureMessage(failure(400))).toBe("Title");
    expect(deleteFailureMessage(failure(400))).toBe("Title");
    expect(imageFailureMessage(failure(400))).toBe("Title");
  });

  it.each([
    [404, "already deleted"],
    [412, "changed by someone else"],
    [503, "not available"],
    [null, "not available"],
  ])("explains delete failure %s", (status, text) => {
    expect(deleteFailureMessage(failure(status))).toContain(text);
  });

  it.each([
    [404, "no image"],
    [412, "changed by someone else"],
    [413, "larger than 5 MB"],
    [415, "JPEG, PNG or WebP"],
    [422, "could not be used"],
    [503, "Image storage is not available"],
    [502, "not available"],
    [null, "not available"],
  ])("explains image failure %s in plain language", (status, text) => {
    expect(imageFailureMessage(failure(status))).toContain(text);
  });

  it("mentions the retry time for unavailable storage", () => {
    expect(imageFailureMessage(failure(503, { retryAfterSeconds: 4 }))).toContain("Try again in 4 seconds");
  });

  it("validates image files on the client", () => {
    expect(validateImageFile({ size: 1000, type: "image/png" })).toBeNull();
    expect(validateImageFile({ size: 5 * 1024 * 1024, type: "image/webp" })).toBeNull();
    expect(validateImageFile({ size: 1000, type: "image/gif" })).toContain("not supported");
    expect(validateImageFile({ size: 1000, type: "" })).toContain("not supported");
    expect(validateImageFile({ size: 5 * 1024 * 1024 + 1, type: "image/jpeg" })).toContain("larger than 5 MB");
    expect(validateImageFile({ size: 0, type: "image/jpeg" })).toBe("The file is empty.");
  });
});


describe("login form helpers", () => {
  it("validates the credentials", () => {
    expect(validateCredentials("a@b.c", "pw")).toBeNull();
    expect(validateCredentials("", "")).toEqual({ email: "Enter your email address", password: "Enter your password" });
    expect(validateCredentials("nope", "pw")).toEqual({ email: "Enter a valid email address" });
  });

  it("explains rate limits with or without the retry time", () => {
    expect(rateLimitedMessage(42)).toBe("Too many sign in attempts. Try again in 42 seconds.");
    expect(rateLimitedMessage(120)).toBe("Too many sign in attempts. Try again in 2 minutes.");
    expect(rateLimitedMessage(undefined)).toBe("Too many sign in attempts. Wait a minute and try again.");
  });

  it("has messages for the redirect reasons", () => {
    expect(Object.keys(LOGIN_REASON_MESSAGES)).toEqual(["forbidden", "expired"]);
  });
});

describe("category and role change messages", () => {
  const failure = (status: number | null, extra: object = {}) => ({
    ok: false as const,
    status,
    title: "Title",
    fieldErrors: {},
    ...extra,
  });

  it.each([
    [409, "already exists"],
    [422, "The category name is not valid."],
    [429, "Too many requests"],
    [503, "not available"],
    [null, "not available"],
    [400, "Detail"],
  ])("explains category failure %s", (status, text) => {
    expect(categoryFailureMessage(failure(status, { detail: "Detail" }))).toContain(text);
  });

  it("prefers the field message for an invalid category and mentions the retry time", () => {
    expect(categoryFailureMessage(failure(422, { fieldErrors: { name: "must not be empty" } }))).toBe("must not be empty");
    expect(categoryFailureMessage(failure(429, { retryAfterSeconds: 9 }))).toContain("Try again in 9 seconds");
    expect(categoryFailureMessage(failure(400))).toBe("Title");
  });

  it.each([
    [404, "no longer exists"],
    [422, "not valid"],
    [503, "not available"],
    [null, "not available"],
    [400, "Detail"],
  ])("explains role change failure %s", (status, text) => {
    expect(roleChangeFailureMessage(failure(status, { detail: "Detail" }))).toContain(text);
  });

  it("explains the self change with the API's advice, or a default", () => {
    expect(roleChangeFailureMessage(failure(409, { detail: "Ask another admin" }))).toBe(
      "You cannot change your own role. Ask another admin",
    );
    expect(roleChangeFailureMessage(failure(409))).toContain("Ask another administrator");
    expect(roleChangeFailureMessage(failure(400))).toBe("Title");
  });
});

describe("import messages", () => {
  const failure = (status: number | null, extra: object = {}) => ({
    ok: false as const,
    status,
    title: "Title",
    fieldErrors: {},
    ...extra,
  });
  const LIMIT = 50 * 1024 * 1024;

  it.each([
    [413, "larger than the 50 MB limit"],
    [401, "session expired"],
    [403, "session expired"],
    [503, "file storage is not available"],
    [502, "not available"],
    [null, "not available"],
    [400, "Detail"],
  ])("explains an upload failure %s", (status, text) => {
    expect(importUploadFailureMessage(failure(status, { detail: "Detail" }), LIMIT)).toContain(text);
  });

  it("uses the server's words for an unreadable upload and the retry time for storage", () => {
    expect(importUploadFailureMessage(failure(422, { detail: "the multipart field 'file' is required" }), LIMIT)).toBe(
      "the multipart field 'file' is required",
    );
    expect(importUploadFailureMessage(failure(415), LIMIT)).toContain("Choose the file again");
    expect(importUploadFailureMessage(failure(503, { retryAfterSeconds: 3 }), LIMIT)).toContain("Try again in 3 seconds");
    expect(importUploadFailureMessage(failure(400), LIMIT)).toBe("Title");
  });

  it.each([
    [404, "no longer exists"],
    [409, "Detail"],
    [503, "not available"],
    [null, "not available"],
    [400, "Detail"],
  ])("explains an import action failure %s", (status, text) => {
    expect(importActionFailureMessage(failure(status, { detail: "Detail" }))).toContain(text);
  });

  it("has defaults for a 409 and a 400 without detail", () => {
    expect(importActionFailureMessage(failure(409))).toContain("no longer in a state");
    expect(importActionFailureMessage(failure(400))).toBe("Title");
  });

  it("tells a missing import from a load problem", () => {
    expect(importLoadFailureMessage(failure(404))).toContain("was not found");
    expect(importLoadFailureMessage(failure(500))).toContain("could not be loaded");
    expect(importLoadFailureMessage(failure(null))).toContain("could not be loaded");
  });
});
