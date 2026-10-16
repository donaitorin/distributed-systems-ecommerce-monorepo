"use server";

import type { LoginState } from "../../lib/login-form";
import { performSignIn } from "../../server/login";

export async function signInAction(previous: LoginState, formData: FormData): Promise<LoginState> {
  return performSignIn(previous, formData);
}
