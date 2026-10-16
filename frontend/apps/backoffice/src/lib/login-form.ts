import { describeRetry } from "./messages";

export type LoginState = {
  email?: string;
  error?: string;
  fieldErrors?: { email?: string; password?: string };
};

export const LOGIN_REASON_MESSAGES: Record<string, string> = {
  forbidden: "This account does not have access to the backoffice.",
  expired: "Your session expired. Sign in again to continue.",
};

export const INCORRECT_CREDENTIALS = "The email or password is incorrect.";
export const SIGN_IN_UNAVAILABLE = "Sign in is not available right now. Try again in a moment.";
export const NO_ADMIN_ACCESS = LOGIN_REASON_MESSAGES.forbidden as string;

export function rateLimitedMessage(retryAfterSeconds: number | undefined): string {
  return retryAfterSeconds === undefined
    ? "Too many sign in attempts. Wait a minute and try again."
    : `Too many sign in attempts. Try again in ${describeRetry(retryAfterSeconds)}.`;
}

export function validateCredentials(email: string, password: string): LoginState["fieldErrors"] | null {
  const fieldErrors: NonNullable<LoginState["fieldErrors"]> = {};
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
