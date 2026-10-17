"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getSession } from "@ecommerce/auth/next";
import type { AddResult, CartResult, ClearResult } from "../../lib/cart";
import { authPageHref, LOGIN_PATH, productHref } from "../../lib/paths";
import { addToCart, clearCart, removeItem, setQuantity } from "../../server/cart";

function refreshHeader(): void {
  revalidatePath("/", "layout");
}

export async function setQuantityAction(sku: string, quantity: number, acceptedPrice?: string): Promise<CartResult> {
  const result = await setQuantity(sku, quantity, acceptedPrice);
  refreshHeader();
  return result;
}

export async function removeItemAction(sku: string): Promise<CartResult> {
  const result = await removeItem(sku);
  refreshHeader();
  return result;
}

export async function clearCartAction(): Promise<ClearResult> {
  const result = await clearCart();
  refreshHeader();
  return result;
}

export async function addToCartAction(sku: string, quantity: number): Promise<AddResult> {
  const returnTo = productHref(sku);
  if ((await getSession()) === null) {
    redirect(authPageHref(LOGIN_PATH, returnTo));
  }
  const result = await addToCart(sku, quantity, returnTo);
  refreshHeader();
  return result;
}
