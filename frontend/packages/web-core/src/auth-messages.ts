import type { FieldError } from "@ecommerce/api-client";
import { describeRetry } from "./retry";

export type CredentialsState = {
  email?: string;
  error?: string;
  fieldErrors?: { email?: string; password?: string };
};

export const INCORRECT_CREDENTIALS = "The email or password is incorrect.";
export const SIGN_IN_UNAVAILABLE = "Sign in is not available right now. Try again in a moment.";
export const EMAIL_TAKEN = "An account with this email already exists. Sign in instead, or use another email.";
export const INVALID_EMAIL = "Enter a valid email address, like name@example.com.";

export function rateLimitedMessage(retryAfterSeconds: number | undefined, activity = "sign in"): string {
  return retryAfterSeconds === undefined
    ? `Too many ${activity} attempts. Wait a minute and try again.`
    : `Too many ${activity} attempts. Try again in ${describeRetry(retryAfterSeconds)}.`;
}

export function validateCredentials(email: string, password: string): CredentialsState["fieldErrors"] | null {
  const fieldErrors: NonNullable<CredentialsState["fieldErrors"]> = {};
  if (email === "") {
    fieldErrors.email = "Enter your email address";
  } else if (!email.includes("@")) {
    fieldErrors.email = "Enter a valid email address";
  }
  if (password === "") {
    fieldErrors.password = "Enter your password";
  }
  return Object.keys(fieldErrors).length > 0 ? fieldErrors : null;
}

const PASSWORD_MESSAGES: Record<string, string> = {
  too_short: "That password is too short. Use at least 10 characters.",
  too_long: "Use at most 128 characters.",
  too_common: "That password is too easy to guess. Choose something less common, such as a few unrelated words.",
  same_as_email: "The password cannot be the same as your email address.",
};
const PASSWORD_FALLBACK = "Choose a different password: this one is not accepted.";

export function passwordProblemMessage(type: string): string {
  return PASSWORD_MESSAGES[type] ?? PASSWORD_FALLBACK;
}

export function registrationFieldErrors(errors: readonly FieldError[]): NonNullable<CredentialsState["fieldErrors"]> {
  const result: NonNullable<CredentialsState["fieldErrors"]> = {};
  for (const { location, type } of errors) {
    if (location === "body.email") {
      result.email ??= INVALID_EMAIL;
    } else if (location === "body.password") {
      result.password ??= passwordProblemMessage(type);
    }
  }
  return result;
}
