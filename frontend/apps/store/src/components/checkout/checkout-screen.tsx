"use client";

import { useRouter } from "next/navigation";
import { orderHref } from "../../lib/paths";
import { CheckoutView, type CheckoutViewProps } from "./checkout-view";

export function CheckoutScreen(props: Omit<CheckoutViewProps, "onPlaced">) {
  const router = useRouter();
  return (
    <CheckoutView
      {...props}
      onPlaced={(orderId) => {
        router.push(orderHref(orderId));
      }}
    />
  );
}
