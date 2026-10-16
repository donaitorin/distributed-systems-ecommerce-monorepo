import { signIn } from "@ecommerce/auth/next";
import { redirect } from "next/navigation";
import {
  INCORRECT_CREDENTIALS,
  NO_ADMIN_ACCESS,
  rateLimitedMessage,
  SIGN_IN_UNAVAILABLE,
  validateCredentials,
  type LoginState,
} from "../lib/login-form";
import { adminNextPath } from "../lib/next-path";
import { REQUIRED_ROLE } from "../lib/paths";

const TOO_MANY_REQUESTS = 429;
const UNAUTHORIZED = 401;

function textOf(formData: FormData, name: string): string {
  const value = formData.get(name);
  return typeof value === "string" ? value : "";
}

export async function performSignIn(_previous: LoginState, formData: FormData): Promise<LoginState> {
  const email = textOf(formData, "email").trim();
  const password = textOf(formData, "password");
  const next = adminNextPath(textOf(formData, "next"));

  const fieldErrors = validateCredentials(email, password);
  if (fieldErrors) {
    return { email, fieldErrors };
  }

  let result;
  try {
    result = await signIn({ email, password });
  } catch {
    return { email, error: SIGN_IN_UNAVAILABLE };
  }

  if (!result.ok) {
    if (result.problem.status === UNAUTHORIZED) {
      return { email, error: INCORRECT_CREDENTIALS };
    }
    if (result.problem.status === TOO_MANY_REQUESTS) {
      return { email, error: rateLimitedMessage(result.retryAfterSeconds) };
    }
    return { email, error: SIGN_IN_UNAVAILABLE };
  }
  if (result.session.role !== REQUIRED_ROLE) {
    return { email, error: NO_ADMIN_ACCESS };
  }
  redirect(next);
}
