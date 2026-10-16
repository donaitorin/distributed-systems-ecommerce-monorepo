"use server";

import type { Failure } from "@ecommerce/web-core";
import type { ProfileFormValues } from "../../lib/account-form";
import { updateProfile, type ProfileSaved } from "../../server/profile";

export async function updateProfileAction(values: ProfileFormValues): Promise<ProfileSaved | Failure> {
  return updateProfile(values);
}
