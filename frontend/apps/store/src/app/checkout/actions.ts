"use server";

import { requireSession } from "@ecommerce/auth/next";
import type { Failure } from "@ecommerce/web-core";
import type { AddressFormValues } from "../../lib/addresses";
import type { PlaceOrderInput, PlaceOrderResult } from "../../lib/checkout";
import { CHECKOUT_PATH, LOGIN_PATH } from "../../lib/paths";
import { addAddress, type AddressSaved } from "../../server/addresses";
import { placeOrder } from "../../server/orders";

export async function placeOrderAction(input: PlaceOrderInput): Promise<PlaceOrderResult> {
  return placeOrder(input);
}

export async function newAttemptKeyAction(): Promise<string> {
  await requireSession({ loginPath: LOGIN_PATH });
  return crypto.randomUUID();
}

export async function addCheckoutAddressAction(values: AddressFormValues): Promise<AddressSaved | Failure> {
  return addAddress(values, CHECKOUT_PATH);
}
