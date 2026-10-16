import type { CredentialsState } from "@ecommerce/web-core";

export type RegisterState = CredentialsState & { emailTaken?: boolean };

export const REGISTER_UNAVAILABLE = "Sign up is not available right now. Try again in a moment.";
export const REGISTERED_BUT_NOT_SIGNED_IN =
  "Your account was created, but we could not sign you in. Sign in with your new email and password.";
export const REGISTER_FAILED = "The account could not be created. Check the fields and try again.";

export const LOGIN_REASON_MESSAGES: Record<string, string> = {
  expired: "Your session expired. Sign in again to continue.",
};
