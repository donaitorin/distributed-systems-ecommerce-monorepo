import "@ecommerce/web-core/zod-config";
import type { AccountsComponents } from "@ecommerce/api-client";
import { z } from "zod";
import { isValidPhone, PHONE_MESSAGE } from "./account-form";

export type Address = AccountsComponents["schemas"]["AddressOut"];
export type AddressBody = AccountsComponents["schemas"]["AddressIn"];

export const MAX_ADDRESSES = 10;
export const COUNTRY_MESSAGE = "Use the two-letter country code, like ES or GB.";
const COUNTRY_PATTERN = /^[A-Za-z]{2}$/;

function required(label: string, max: number) {
  return z.string().trim().min(1, `Enter ${label}`).max(max, `Use at most ${max} characters`);
}

function optional(max: number) {
  return z.string().trim().max(max, `Use at most ${max} characters`);
}

export const addressFormSchema = z.object({
  recipient_name: required("the name of the person who receives the order", 100),
  line1: required("the street address", 200),
  line2: optional(200),
  city: required("the city", 100),
  region: optional(200),
  postal_code: required("the postal code", 20),
  country: z.string().trim().regex(COUNTRY_PATTERN, COUNTRY_MESSAGE),
  phone: z.string().trim().refine(isValidPhone, PHONE_MESSAGE),
});

export type AddressFormValues = z.infer<typeof addressFormSchema>;
export type AddressField = keyof AddressFormValues;

export const ADDRESS_FIELDS: readonly AddressField[] = [
  "recipient_name",
  "line1",
  "line2",
  "city",
  "region",
  "postal_code",
  "country",
  "phone",
];

export const EMPTY_ADDRESS: AddressFormValues = {
  recipient_name: "",
  line1: "",
  line2: "",
  city: "",
  region: "",
  postal_code: "",
  country: "",
  phone: "",
};

function blankToNull(value: string): string | null {
  return value === "" ? null : value;
}

export function toAddressBody(values: AddressFormValues): AddressBody {
  return {
    recipient_name: values.recipient_name,
    line1: values.line1,
    line2: blankToNull(values.line2),
    city: values.city,
    region: blankToNull(values.region),
    postal_code: values.postal_code,
    country: values.country.toUpperCase(),
    phone: blankToNull(values.phone),
  };
}

export function addressFieldErrors(fieldErrors: Record<string, string>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const field of ADDRESS_FIELDS) {
    const message = fieldErrors[field];
    if (message !== undefined) {
      result[field] = field === "phone" ? PHONE_MESSAGE : field === "country" ? COUNTRY_MESSAGE : message;
    }
  }
  return result;
}

export function addressLines(address: Pick<Address, "line1" | "line2" | "city" | "region" | "postal_code" | "country">): string[] {
  const place = [address.city, address.region, address.postal_code].filter(Boolean).join(", ");
  return [address.line1, address.line2, place, address.country].filter((line): line is string => Boolean(line));
}

export function addressSummary(address: Address): string {
  return [address.recipient_name, ...addressLines(address)].join(", ");
}

export function addressFailureMessage(status: number | null): string {
  if (status === 409) {
    return `You already have ${MAX_ADDRESSES} saved addresses. Delete one to add another.`;
  }
  if (status === 422) {
    return "Some fields need attention. Check the highlighted fields and try again.";
  }
  if (status === 429) {
    return "Too many requests. Wait a moment and try again.";
  }
  return "The address could not be saved right now. Try again in a moment.";
}
