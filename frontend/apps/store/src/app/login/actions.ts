"use server";

import type { CredentialsState } from "@ecommerce/web-core";
import { performSignIn } from "../../server/login";

export async function signInAction(previous: CredentialsState, formData: FormData): Promise<CredentialsState> {
  return performSignIn(previous, formData);
}
