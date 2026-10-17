import "@ecommerce/web-core/zod-config";
import type { AccountsComponents } from "@ecommerce/api-client";
import { z } from "zod";

export type Profile = AccountsComponents["schemas"]["ProfileOut"];

export const NAME_MAX_LENGTH = 100;
const PHONE_SEPARATORS = /[\s\-.()]/g;
const PHONE_PATTERN = /^\+\d{8,15}$/;

export const PHONE_MESSAGE = "Start with + and the country code, then 8 to 15 digits in total, like +34 600 123 456.";

export function isValidPhone(value: string): boolean {
  return value === "" || PHONE_PATTERN.test(value.replace(PHONE_SEPARATORS, ""));
}

export const profileFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter your name")
    .max(NAME_MAX_LENGTH, `Use at most ${NAME_MAX_LENGTH} characters`),
  phone: z
    .string()
    .trim()
    .refine(isValidPhone, PHONE_MESSAGE),
});

export type ProfileFormValues = z.infer<typeof profileFormSchema>;
export type ProfileField = keyof ProfileFormValues;

export const PROFILE_FIELDS: readonly ProfileField[] = ["name", "phone"];

export function profileToFormValues(profile: Pick<Profile, "name" | "phone">): ProfileFormValues {
  return { name: profile.name ?? "", phone: profile.phone ?? "" };
}

export function toPatchBody(values: ProfileFormValues): { name: string; phone: string | null } {
  return { name: values.name, phone: values.phone === "" ? null : values.phone };
}

export function profileFieldErrors(fieldErrors: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const field of PROFILE_FIELDS) {
    const message = fieldErrors[field];
    if (message !== undefined) {
      result[field] = field === "phone" ? PHONE_MESSAGE : message;
    }
  }
  return result;
}
