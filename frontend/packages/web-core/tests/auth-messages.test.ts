/**
 * @jest-environment node
 */
import {
  passwordProblemMessage,
  rateLimitedMessage,
  registrationFieldErrors,
  validateCredentials,
  EMAIL_TAKEN,
  INVALID_EMAIL,
} from "../src";

describe("validateCredentials", () => {
  it("asks for missing and malformed values", () => {
    expect(validateCredentials("", "")).toEqual({
      email: "Enter your email address",
      password: "Enter your password",
    });
    expect(validateCredentials("ada", "x")).toEqual({ email: "Enter a valid email address" });
    expect(validateCredentials("ada@example.com", "x")).toBeNull();
  });
});

describe("rateLimitedMessage", () => {
  it("says when to retry and defaults to sign in attempts", () => {
    expect(rateLimitedMessage(42)).toBe("Too many sign in attempts. Try again in 42 seconds.");
    expect(rateLimitedMessage(undefined)).toBe("Too many sign in attempts. Wait a minute and try again.");
  });

  it("names the activity", () => {
    expect(rateLimitedMessage(120, "sign up")).toBe("Too many sign up attempts. Try again in 2 minutes.");
  });
});

describe("password problems in plain language", () => {
  it.each([
    ["too_short", "at least 10 characters"],
    ["too_long", "at most 128"],
    ["too_common", "too easy to guess"],
    ["same_as_email", "cannot be the same as your email"],
    ["something_new", "not accepted"],
  ])("explains %s", (type, text) => {
    expect(passwordProblemMessage(type)).toContain(text);
  });

  it("keeps the technical wording of the API out of the messages", () => {
    expect(passwordProblemMessage("too_short")).not.toMatch(/must be|too_short/);
  });
});

describe("registrationFieldErrors", () => {
  it("maps the API's field errors to the form fields, keeping the first per field", () => {
    expect(
      registrationFieldErrors([
        { location: "body.password", message: "must be at least 10 characters", type: "too_short" },
        { location: "body.password", message: "is too common", type: "too_common" },
        { location: "body.email", message: "must contain exactly one @", type: "invalid_email" },
        { location: "query.other", message: "ignored", type: "x" },
      ]),
    ).toEqual({
      password: expect.stringContaining("at least 10 characters") as string,
      email: INVALID_EMAIL,
    });
  });

  it("is empty without errors", () => {
    expect(registrationFieldErrors([])).toEqual({});
    expect(EMAIL_TAKEN).toContain("already exists");
  });
});
