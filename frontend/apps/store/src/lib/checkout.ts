import "@ecommerce/web-core/zod-config";
import { z } from "zod";
import { describeRetry } from "@ecommerce/web-core";
import type { Cart, CartLine } from "./cart";

export const CARD_MIN_DIGITS = 12;
export const CARD_MAX_DIGITS = 19;
const CARD_GROUP = 4;
const CARD_CHARACTERS = /^[\d\s-]*$/;
const ATTEMPT_KEY = /^[A-Za-z0-9_:.-]{8,128}$/;

export const CARD_MESSAGE = `Enter the ${CARD_MIN_DIGITS} to ${CARD_MAX_DIGITS} digits of the card number. Digits only.`;

export const TEST_CARDS = [
  { ending: "1111", outcome: "approves the payment" },
  { ending: "0000", outcome: "declines the payment" },
  { ending: "9999", outcome: "never answers, so the order is cancelled after about a minute" },
  { ending: "2222", outcome: "approves late: the order is cancelled and the payment refunded" },
] as const;

export function cardDigits(text: string): string {
  return text.replace(/\D/g, "").slice(0, CARD_MAX_DIGITS);
}

export function groupCardNumber(text: string): string {
  return cardDigits(text).match(/.{1,4}/g)?.join(" ") ?? "";
}

export function lastFour(digits: string): string {
  return digits.slice(-CARD_GROUP);
}

export function isValidCardNumber(text: string): boolean {
  const digits = text.replace(/[\s-]/g, "");
  return CARD_CHARACTERS.test(text) && digits.length >= CARD_MIN_DIGITS && digits.length <= CARD_MAX_DIGITS;
}

export const checkoutFormSchema = z.object({
  card_number: z.string().refine(isValidCardNumber, CARD_MESSAGE),
});

export type CheckoutFormValues = z.infer<typeof checkoutFormSchema>;

export function isAttemptKey(value: unknown): value is string {
  return typeof value === "string" && ATTEMPT_KEY.test(value);
}

export function cartFingerprint(cart: Pick<Cart, "items">): string {
  return cart.items.map((line) => `${line.sku}:${line.quantity}:${line.price}`).join(",");
}

export function blockedLines(cart: Pick<Cart, "items">): CartLine[] {
  return cart.items.filter((line) => line.flags.length > 0);
}

export type PlaceOrderInput = {
  attemptKey: string;
  addressId: string;
  cardNumber: string;
  cartFingerprint: string;
};

export type PlaceOrderFailureKind =
  | "empty_cart"
  | "cart_flagged"
  | "cart_changed"
  | "address_missing"
  | "attempt_changed"
  | "invalid_card"
  | "invalid_address"
  | "invalid"
  | "rate_limited"
  | "unavailable";

export type PlaceOrderFailure = {
  ok: false;
  kind: PlaceOrderFailureKind;
  fieldErrors?: Record<string, string>;
  retryAfterSeconds?: number;
};

export type PlaceOrderResult = { ok: true; orderId: string } | PlaceOrderFailure;

export function placeOrderFailureMessage(failure: PlaceOrderFailure): string {
  switch (failure.kind) {
    case "empty_cart":
      return "Your cart is empty, so there is nothing to order.";
    case "cart_flagged":
      return "Some items in your cart need your attention. Go back to your cart to resolve them.";
    case "cart_changed":
      return "Your cart changed since this page loaded. Reload the page to review it, then place the order again.";
    case "address_missing":
      return "That shipping address is no longer saved. Choose another address or add a new one.";
    case "attempt_changed":
      return "Something changed since your last try, so nothing was ordered. Check the details and place the order again.";
    case "invalid_card":
      return "The card number is not valid. Check it and try again. Nothing was charged.";
    case "invalid_address":
      return "The selected address cannot be used for an order. Add a corrected address and choose it.";
    case "invalid":
      return "The order could not be accepted. Review your cart and address, then try again. Nothing was charged.";
    case "rate_limited":
      return failure.retryAfterSeconds
        ? `Too many attempts. Wait ${describeRetry(failure.retryAfterSeconds)} and try again.`
        : "Too many attempts. Wait a moment and try again.";
    case "unavailable":
      return "We could not reach the order service, so your order may not have been placed. Enter your card again and press Place order. Repeating the same attempt never creates a second order.";
  }
}

export type Attempt = { key: string; signature: string | null };

export function attemptSignature(parts: { cartFingerprint: string; addressId: string; cardDigits: string }): string {
  return [parts.cartFingerprint, parts.addressId, lastFour(parts.cardDigits)].join("|");
}

export async function nextAttempt(
  current: Attempt,
  signature: string,
  newKey: () => Promise<string>,
): Promise<Attempt> {
  if (current.signature === null) {
    return { key: current.key, signature };
  }
  if (current.signature === signature) {
    return current;
  }
  return { key: await newKey(), signature };
}
