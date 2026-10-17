import type { CartComponents } from "@ecommerce/api-client";
import { formatPrice } from "@ecommerce/ui";

export type Cart = CartComponents["schemas"]["CartOut"];
export type CartLine = CartComponents["schemas"]["LineOut"];
export type CartFlag = CartComponents["schemas"]["FlagOut"];

export const MIN_QUANTITY = 1;
export const MAX_QUANTITY = 99;
export const MAX_LINES = 100;

export type CartFailureKind = "cart_full" | "price_changed" | "not_found" | "invalid" | "unavailable";

export type CartFailure = {
  ok: false;
  kind: CartFailureKind;
  currentPrice?: string;
  retryAfterSeconds?: number;
};

export type CartUpdated = { ok: true; cart: Cart };
export type CartCleared = { ok: true };
export type ItemAdded = { ok: true; quantity: number; capped: boolean };

export type CartResult = CartUpdated | CartFailure;
export type ClearResult = CartCleared | CartFailure;
export type AddResult = ItemAdded | CartFailure;

export type CartActions = {
  setQuantity: (sku: string, quantity: number, acceptedPrice?: string) => Promise<CartResult>;
  removeItem: (sku: string) => Promise<CartResult>;
  clearCart: () => Promise<ClearResult>;
};

export type AddToCart = (sku: string, quantity: number) => Promise<AddResult>;

export function isCartFailure(result: Cart | CartFailure): result is CartFailure {
  return "ok" in result;
}

const WHOLE_NUMBER = /^\d{1,3}$/;

export function parseQuantity(text: string): number | null {
  const trimmed = text.trim();
  if (!WHOLE_NUMBER.test(trimmed)) {
    return null;
  }
  const value = Number(trimmed);
  return value >= MIN_QUANTITY && value <= MAX_QUANTITY ? value : null;
}

export function isValidQuantity(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= MIN_QUANTITY && value <= MAX_QUANTITY;
}

export const QUANTITY_ERROR = `Enter a whole number from ${MIN_QUANTITY} to ${MAX_QUANTITY}.`;

export function money(amount: string): string {
  return formatPrice(amount, "USD") ?? `$${amount}`;
}

export function pluralItems(count: number): string {
  return `${count} ${count === 1 ? "item" : "items"}`;
}

export function failureMessage(failure: CartFailure): string {
  switch (failure.kind) {
    case "cart_full":
      return `Your cart already has ${MAX_LINES} different products. Remove one to add another.`;
    case "not_found":
      return "This product is no longer available.";
    case "invalid":
      return `Choose a quantity from ${MIN_QUANTITY} to ${MAX_QUANTITY}.`;
    case "price_changed":
      return failure.currentPrice
        ? `The price is now ${money(failure.currentPrice)}. Review it and accept the new price to keep this item.`
        : "The price changed. Review it and accept the new price to keep this item.";
    case "unavailable":
      return "The cart could not be reached right now. Nothing was changed. Try again in a moment.";
  }
}

export type FlagNotice = { label: string; text: string; acceptablePrice?: string };

export function describeFlag(flag: CartFlag, override?: string): FlagNotice {
  switch (flag.type) {
    case "price_changed": {
      const next = override ?? flag.new_price ?? "";
      return {
        label: "Price changed",
        text: `The price changed from ${money(flag.old_price ?? "")} to ${money(next)}.`,
        acceptablePrice: next,
      };
    }
    case "unavailable":
      return { label: "No longer available", text: "This product is no longer available. Remove it to continue." };
    case "insufficient_stock":
      return flag.available && flag.available > 0
        ? { label: "Low stock", text: `Only ${flag.available} left. Lower the quantity or remove it.` }
        : { label: "Out of stock", text: "This product is out of stock. Remove it or come back later." };
  }
}
