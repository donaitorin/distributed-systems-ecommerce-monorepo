"use client";

import { useState, useTransition } from "react";
import { Button } from "@ecommerce/ui";
import {
  failureMessage,
  MAX_QUANTITY,
  type AddToCart,
  type CartFailure,
} from "../../lib/cart";
import { CART_PATH } from "../../lib/paths";
import { QuantityControl } from "./quantity-control";

export type AddToCartFormProps = {
  sku: string;
  name: string;
  stock: number;
  add: AddToCart;
};

type Outcome = { kind: "added"; quantity: number; capped: boolean } | { kind: "failed"; failure: CartFailure };

function outcomeText(outcome: Outcome): string {
  if (outcome.kind === "failed") {
    return failureMessage(outcome.failure);
  }
  return outcome.capped
    ? `Added. Your cart now holds ${outcome.quantity}, the most you can have of one product.`
    : `Added to your cart. You now have ${outcome.quantity} in your cart.`;
}

export function AddToCartForm({ sku, name, stock, add }: AddToCartFormProps) {
  const soldOut = stock <= 0;
  const max = Math.min(MAX_QUANTITY, Math.max(stock, 1));
  const [quantity, setQuantity] = useState(1);
  const [outcome, setOutcome] = useState<Outcome>();
  const [pending, startTransition] = useTransition();

  const submit = () => {
    setOutcome(undefined);
    startTransition(async () => {
      const result = await add(sku, quantity);
      setOutcome(result.ok ? { kind: "added", quantity: result.quantity, capped: result.capped } : { kind: "failed", failure: result });
    });
  };

  return (
    <form
      aria-label={`Add ${name} to your cart`}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (!soldOut) {
          submit();
        }
      }}
      className="flex flex-col gap-3"
    >
      {soldOut ? (
        <p id="add-to-cart-unavailable" className="max-w-prose text-base font-medium text-danger-strong">
          This product is out of stock and cannot be added to a cart.
        </p>
      ) : (
        <QuantityControl name={name} value={quantity} onChange={setQuantity} max={max} disabled={pending} />
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={soldOut} loading={pending}>
          Add to cart
        </Button>
        {outcome?.kind === "added" ? (
          <a href={CART_PATH} className="text-sm font-medium text-accent-strong underline">
            View cart
          </a>
        ) : null}
      </div>
      <p role="status" className="text-sm font-medium text-success-strong">
        {outcome?.kind === "added" ? outcomeText(outcome) : ""}
      </p>
      {outcome?.kind === "failed" ? (
        <p role="alert" className="max-w-prose text-sm font-medium text-danger-strong">
          {outcomeText(outcome)}
        </p>
      ) : null}
    </form>
  );
}
