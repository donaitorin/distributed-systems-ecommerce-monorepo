import { redirect } from "next/navigation";
import { isFailure, settle, type Failure } from "@ecommerce/web-core";
import { addressFieldErrors, addressFormSchema, toAddressBody, type Address, type AddressFormValues } from "../lib/addresses";
import { LOGIN_PATH } from "../lib/paths";
import type { ACCOUNT_PATH, CHECKOUT_PATH } from "../lib/paths";
import { accountsApi } from "./accounts";

const UNAUTHORIZED = 401;
const NOT_FOUND = 404;
const UNPROCESSABLE = 422;
const ADDRESS_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type AddressReturn = typeof ACCOUNT_PATH | typeof CHECKOUT_PATH;
export type AddressSaved = { ok: true; address: Address };
export type AddressRemoved = { ok: true };

function expiredSession(returnTo: AddressReturn): never {
  return redirect(`${LOGIN_PATH}?next=${encodeURIComponent(returnTo)}&reason=expired`);
}

async function guarded<Value>(returnTo: AddressReturn, work: () => Promise<Value>): Promise<Value | Failure> {
  const result = await settle(work);
  if (isFailure(result) && result.status === UNAUTHORIZED) {
    expiredSession(returnTo);
  }
  return result;
}

export function loadAddresses(returnTo: AddressReturn): Promise<Address[] | Failure> {
  return guarded(returnTo, async () => {
    const { data } = await accountsApi().get("/api/v1/accounts/me/addresses");
    return data.items;
  });
}

export async function addAddress(values: AddressFormValues, returnTo: AddressReturn): Promise<AddressSaved | Failure> {
  const parsed = addressFormSchema.safeParse(values);
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
  const result = await guarded(returnTo, async () => {
    const { data } = await accountsApi().post("/api/v1/accounts/me/addresses", { body: toAddressBody(parsed.data) });
    return data;
  });
  if (isFailure(result)) {
    return { ...result, fieldErrors: addressFieldErrors(result.fieldErrors) };
  }
  return { ok: true, address: result };
}

export async function removeAddress(addressId: string, returnTo: AddressReturn): Promise<AddressRemoved | Failure> {
  if (!ADDRESS_ID.test(addressId)) {
    return { ok: false, status: NOT_FOUND, title: "Address not found", fieldErrors: {} };
  }
  const result = await guarded(returnTo, async () => {
    await accountsApi().delete("/api/v1/accounts/me/addresses/{address_id}", { params: { address_id: addressId } });
    return { ok: true } as const;
  });
  return isFailure(result) && result.status === NOT_FOUND ? { ok: true } : result;
}
