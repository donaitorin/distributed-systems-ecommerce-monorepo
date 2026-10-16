import { redirect } from "next/navigation";
import { isFailure, settle, type Failure } from "@ecommerce/web-core";
import {
  profileFieldErrors,
  profileFormSchema,
  toPatchBody,
  type Profile,
  type ProfileFormValues,
} from "../lib/account-form";
import { ACCOUNT_PATH, LOGIN_PATH } from "../lib/paths";
import { accountsApi } from "./accounts";

const UNAUTHORIZED = 401;
const UNPROCESSABLE = 422;

export type ProfileSaved = { ok: true; profile: Profile };

function expiredSession(): never {
  return redirect(`${LOGIN_PATH}?next=${encodeURIComponent(ACCOUNT_PATH)}&reason=expired`);
}

async function guarded<Value>(work: () => Promise<Value>): Promise<Value | Failure> {
  const result = await settle(work);
  if (isFailure(result) && result.status === UNAUTHORIZED) {
    expiredSession();
  }
  return result;
}

export function loadProfile(): Promise<Profile | Failure> {
  return guarded(async () => {
    const { data } = await accountsApi().get("/api/v1/accounts/me");
    return data;
  });
}

export async function updateProfile(values: ProfileFormValues): Promise<ProfileSaved | Failure> {
  const parsed = profileFormSchema.safeParse(values);
  if (!parsed.success) {
    const fieldErrors: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      const field = issue.path[0];
      if (typeof field === "string") {
        fieldErrors[field] ??= issue.message;
      }
    }
    return { ok: false, status: UNPROCESSABLE, title: "Validation failed", fieldErrors };
  }
  const result = await guarded(async () => {
    const { data } = await accountsApi().patch("/api/v1/accounts/me", { body: toPatchBody(parsed.data) });
    return data;
  });
  if (isFailure(result)) {
    return { ...result, fieldErrors: profileFieldErrors(result.fieldErrors) };
  }
  return { ok: true, profile: result };
}
