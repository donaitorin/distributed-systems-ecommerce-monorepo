"use client";

import { useState } from "react";
import { CART_PATH } from "../../lib/paths";
import { pluralItems } from "../../lib/cart";

function CartIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className="size-5 shrink-0"
    >
      <circle cx="9" cy="20" r="1.5" />
      <circle cx="18" cy="20" r="1.5" />
      <path d="M2 3h3l2.7 11.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 7H6" />
    </svg>
  );
}

function announcementFor(count: number): string {
  return count === 0 ? "Your cart is empty." : `Cart updated: ${pluralItems(count)} in your cart.`;
}

export function CartLink({ count }: { count: number | null }) {
  const [announced, setAnnounced] = useState<{ count: number | null; text: string }>({ count, text: "" });
  if (announced.count !== count) {
    setAnnounced({ count, text: count === null ? "" : announcementFor(count) });
  }

  return (
    <>
      <a
        href={CART_PATH}
        className="inline-flex min-h-11 items-center gap-2 rounded-md px-3 text-sm font-medium text-primary hover:bg-surface-2"
      >
        <CartIcon />
        <span>Cart</span>
        {count !== null && count > 0 ? (
          <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-accent-strong px-2 py-0.5 text-xs font-semibold text-on-accent">
            {count}
            <span className="sr-only"> {count === 1 ? "item" : "items"} in your cart</span>
          </span>
        ) : null}
      </a>
      <span role="status" aria-live="polite" className="sr-only">
        {announced.text}
      </span>
    </>
  );
}
