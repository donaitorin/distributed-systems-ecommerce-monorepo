"use client";

import { useRef, useState, useTransition } from "react";
import { Button, ButtonLink, ConfirmDialog, EmptyState } from "@ecommerce/ui";
import {
  failureMessage,
  money,
  pluralItems,
  type Cart,
  type CartActions,
  type CartFailure,
  type CartResult,
  type ClearResult,
} from "../../lib/cart";
import { CHECKOUT_PATH, PRODUCTS_PATH } from "../../lib/paths";
import { CartLineItem } from "./cart-line-item";

export type CartViewProps = {
  cart: Cart;
  actions: CartActions;
};

type Problem = { message: string; retry?: () => void };

export function CartView({ cart, actions }: CartViewProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [status, setStatus] = useState("");
  const [problem, setProblem] = useState<Problem>();
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [clearError, setClearError] = useState<string>();
  const [pending, startTransition] = useTransition();

  const attempt = (
    work: () => Promise<CartResult>,
    sku: string,
    success: string,
    retry: () => void,
  ) => {
    setStatus("");
    setProblem(undefined);
    startTransition(async () => {
      const result = await work();
      if (result.ok) {
        setStatus(success);
        setOverrides((current) => Object.fromEntries(Object.entries(current).filter(([key]) => key !== sku)));
        if (result.cart.items.length === 0) {
          headingRef.current?.focus();
        }
        return;
      }
      reportFailure(result, sku, retry);
    });
  };

  const reportFailure = (failure: CartFailure, sku: string, retry: () => void) => {
    if (failure.kind === "price_changed" && failure.currentPrice) {
      setOverrides((current) => ({ ...current, [sku]: failure.currentPrice ?? "" }));
    }
    setProblem({ message: failureMessage(failure), ...(failure.kind === "unavailable" ? { retry } : {}) });
  };

  const changeQuantity = (sku: string, name: string, quantity: number) => {
    attempt(
      () => actions.setQuantity(sku, quantity),
      sku,
      `Quantity of ${name} set to ${quantity}.`,
      () => {
        changeQuantity(sku, name, quantity);
      },
    );
  };

  const remove = (sku: string, name: string) => {
    attempt(
      () => actions.removeItem(sku),
      sku,
      `${name} removed from your cart.`,
      () => {
        remove(sku, name);
      },
    );
  };

  const acceptPrice = (sku: string, name: string, quantity: number, price: string) => {
    attempt(
      () => actions.setQuantity(sku, quantity, price),
      sku,
      `The price of ${name} is now ${money(price)}.`,
      () => {
        acceptPrice(sku, name, quantity, price);
      },
    );
  };

  const clear = () => {
    setClearError(undefined);
    startTransition(async () => {
      const result: ClearResult = await actions.clearCart();
      if (result.ok) {
        setConfirmOpen(false);
        setStatus("Your cart is empty.");
        setProblem(undefined);
        headingRef.current?.focus();
        return;
      }
      setClearError(failureMessage(result));
    });
  };

  const empty = cart.items.length === 0;

  return (
    <section aria-labelledby="cart-heading" className="flex flex-col gap-6" aria-busy={pending || undefined}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id="cart-heading" ref={headingRef} tabIndex={-1} className="text-3xl font-semibold">
          Your cart
        </h1>
        {empty ? null : (
          <Button
            variant="secondary"
            disabled={pending}
            onClick={() => {
              setClearError(undefined);
              setConfirmOpen(true);
            }}
          >
            Clear cart
          </Button>
        )}
      </div>
      <p role="status" className="min-h-5 text-sm font-medium text-success-strong">
        {status}
      </p>
      {problem ? (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-2 border-danger-strong p-3 text-sm font-medium text-danger-strong">
          <p>{problem.message}</p>
          {problem.retry ? (
            <Button variant="secondary" onClick={problem.retry}>
              Try again
            </Button>
          ) : null}
        </div>
      ) : null}
      {empty ? (
        <EmptyState
          title="Your cart is empty"
          description="Add a product from the catalog and it will show up here."
          action={<ButtonLink href={PRODUCTS_PATH}>Browse products</ButtonLink>}
        />
      ) : (
        <>
          <ul className="flex flex-col gap-4" aria-label="Items in your cart">
            {cart.items.map((line) => (
              <CartLineItem
                key={line.sku}
                line={line}
                disabled={pending}
                {...(overrides[line.sku] ? { priceOverride: overrides[line.sku] } : {})}
                onQuantity={(quantity) => {
                  changeQuantity(line.sku, line.name, quantity);
                }}
                onRemove={() => {
                  remove(line.sku, line.name);
                }}
                onAcceptPrice={(price) => {
                  acceptPrice(line.sku, line.name, line.quantity, price);
                }}
              />
            ))}
          </ul>
          <div className="flex max-w-md flex-col gap-2 border-t border-border pt-4">
            <dl>
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-base font-medium">Subtotal ({pluralItems(cart.item_count)})</dt>
                <dd className="text-xl font-semibold">{money(cart.subtotal)}</dd>
              </div>
            </dl>
            <p className="text-sm text-secondary">Prices and stock are checked again when you check out.</p>
            <div>
              <ButtonLink href={CHECKOUT_PATH}>Checkout</ButtonLink>
            </div>
          </div>
        </>
      )}
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Clear your cart?"
        description={`This removes all ${pluralItems(cart.item_count)} from your cart.`}
        confirmLabel="Clear cart"
        variant="danger"
        pending={pending}
        {...(clearError ? { error: clearError } : {})}
        onConfirm={clear}
      />
    </section>
  );
}
