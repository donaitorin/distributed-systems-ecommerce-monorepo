export {
  INCORRECT_CREDENTIALS,
  rateLimitedMessage,
  SIGN_IN_UNAVAILABLE,
  validateCredentials,
  type CredentialsState as LoginState,
} from "@ecommerce/web-core";

export const LOGIN_REASON_MESSAGES: Record<string, string> = {
  forbidden: "This account does not have access to the backoffice.",
  expired: "Your session expired. Sign in again to continue.",
};

export const NO_ADMIN_ACCESS = LOGIN_REASON_MESSAGES.forbidden as string;
