"use server";

import type { RegisterState } from "../../lib/auth-form";
import { performRegister } from "../../server/register";

export async function registerAction(previous: RegisterState, formData: FormData): Promise<RegisterState> {
  return performRegister(previous, formData);
}
