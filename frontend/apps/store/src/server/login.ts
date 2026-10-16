import { signIn } from "@ecommerce/auth/next";
import { redirect } from "next/navigation";
import {
  INCORRECT_CREDENTIALS,
  rateLimitedMessage,
  SIGN_IN_UNAVAILABLE,
  validateCredentials,
  type CredentialsState,
} from "@ecommerce/web-core";
import { storeNextPath } from "../lib/paths";
import { textOf } from "./form-data";

const TOO_MANY_REQUESTS = 429;
const UNAUTHORIZED = 401;

export async function performSignIn(_previous: CredentialsState, formData: FormData): Promise<CredentialsState> {
  const email = textOf(formData, "email").trim();
  const password = textOf(formData, "password");
  const next = storeNextPath(textOf(formData, "next"));

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
  redirect(next);
}
