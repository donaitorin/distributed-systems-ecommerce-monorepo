import { registerAccount, signIn } from "@ecommerce/auth/next";
import { redirect } from "next/navigation";
import {
  EMAIL_TAKEN,
  rateLimitedMessage,
  registrationFieldErrors,
  validateCredentials,
} from "@ecommerce/web-core";
import {
  REGISTER_FAILED,
  REGISTER_UNAVAILABLE,
  REGISTERED_BUT_NOT_SIGNED_IN,
  type RegisterState,
} from "../lib/auth-form";
import { storeNextPath } from "../lib/paths";
import { textOf } from "./form-data";

const TOO_MANY_REQUESTS = 429;
const CONFLICT = 409;
const UNPROCESSABLE = 422;

async function signInAfterRegistering(email: string, password: string): Promise<boolean> {
  try {
    return (await signIn({ email, password })).ok;
  } catch {
    return false;
  }
}

export async function performRegister(_previous: RegisterState, formData: FormData): Promise<RegisterState> {
  const email = textOf(formData, "email").trim();
  const password = textOf(formData, "password");
  const next = storeNextPath(textOf(formData, "next"));

  const fieldErrors = validateCredentials(email, password);
  if (fieldErrors) {
    return { email, fieldErrors };
  }

  let result;
  try {
    result = await registerAccount({ email, password });
  } catch {
    return { email, error: REGISTER_UNAVAILABLE };
  }

  if (!result.ok) {
    const { status, errors } = result.problem;
    if (status === CONFLICT) {
      return { email, fieldErrors: { email: EMAIL_TAKEN }, emailTaken: true };
    }
    if (status === UNPROCESSABLE) {
      const details = registrationFieldErrors(errors ?? []);
      return Object.keys(details).length > 0 ? { email, fieldErrors: details } : { email, error: REGISTER_FAILED };
    }
    if (status === TOO_MANY_REQUESTS) {
      return { email, error: rateLimitedMessage(result.retryAfterSeconds, "sign up") };
    }
    return { email, error: REGISTER_UNAVAILABLE };
  }

  if (!(await signInAfterRegistering(email, password))) {
    return { email, error: REGISTERED_BUT_NOT_SIGNED_IN };
  }
  redirect(next);
}
