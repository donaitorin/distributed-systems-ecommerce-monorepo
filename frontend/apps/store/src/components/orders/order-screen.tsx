"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { LOGIN_PATH, orderHref } from "../../lib/paths";
import { OrderTracker, type OrderTrackerProps } from "./order-tracker";

export function OrderScreen(props: Omit<OrderTrackerProps, "onSessionExpired">) {
  const router = useRouter();
  const orderId = props.initial.id;
  const expired = useCallback(() => {
    router.replace(`${LOGIN_PATH}?next=${encodeURIComponent(orderHref(orderId))}&reason=expired`);
  }, [router, orderId]);
  return <OrderTracker {...props} onSessionExpired={expired} />;
}
