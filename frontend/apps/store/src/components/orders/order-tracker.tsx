"use client";

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { ButtonLink } from "@ecommerce/ui";
import { fetchOrder as defaultFetchOrder, isTerminalRequestError, OrderRequestError, SESSION_EXPIRED, type OrderFetcher } from "../../lib/order-client";
import { awaitsRefund, isFinalStatus, pollDelay, shouldKeepPolling, type Order } from "../../lib/orders";
import { PRODUCTS_PATH } from "../../lib/paths";
import { OrderDetails } from "./order-details";
import { OrderStatusBanner } from "./order-status-banner";

export type OrderTrackerProps = {
  initial: Order;
  fetchOrder?: OrderFetcher;
  onConfirmed?: () => Promise<void> | void;
  onSessionExpired: () => void;
};

const HEADER_REFRESH_DELAYS_MS = [0, 2000, 6000];
const RETRIES = 2;
const RETRY_BASE_MS = 1000;
const RETRY_MAX_MS = 8000;

function Tracker({ initial, fetchOrder = defaultFetchOrder, onConfirmed, onSessionExpired }: OrderTrackerProps) {
  const { data: order, error } = useQuery({
    queryKey: ["order", initial.id],
    queryFn: ({ signal }) => fetchOrder(initial.id, signal),
    initialData: initial,
    refetchInterval: (query) => {
      const current = query.state.data;
      if ((current && !shouldKeepPolling(current, Date.now())) || isTerminalRequestError(query.state.error)) {
        return false;
      }
      return pollDelay(query.state.dataUpdateCount);
    },
    retry: (count, failure) => !isTerminalRequestError(failure) && count < RETRIES,
    retryDelay: (count) => Math.min(RETRY_BASE_MS * 2 ** count, RETRY_MAX_MS),
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (error instanceof OrderRequestError && error.status === SESSION_EXPIRED) {
      onSessionExpired();
    }
  }, [error, onSessionExpired]);

  const confirmed = order.status === "CONFIRMED";
  useEffect(() => {
    if (!confirmed || !onConfirmed) {
      return;
    }
    const timers = HEADER_REFRESH_DELAYS_MS.map((delay) =>
      setTimeout(() => {
        void onConfirmed();
      }, delay),
    );
    return () => {
      timers.forEach(clearTimeout);
    };
  }, [confirmed, onConfirmed]);

  const stale = error !== null && (!isFinalStatus(order.status) || awaitsRefund(order));

  return (
    <section aria-labelledby="order-heading" className="flex flex-col gap-6">
      <h1 id="order-heading" className="text-3xl font-semibold">
        Order {order.id.slice(0, 8).toUpperCase()}
      </h1>
      <OrderStatusBanner order={order} />
      {stale ? (
        <p className="text-sm font-medium text-secondary">
          We cannot refresh the status right now. We will keep trying. The status shown may be out of date.
        </p>
      ) : null}
      <OrderDetails order={order} />
      <div>
        <ButtonLink href={PRODUCTS_PATH} variant="secondary">
          Continue shopping
        </ButtonLink>
      </div>
    </section>
  );
}

export function OrderTracker(props: OrderTrackerProps) {
  const [client] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={client}>
      <Tracker {...props} />
    </QueryClientProvider>
  );
}
