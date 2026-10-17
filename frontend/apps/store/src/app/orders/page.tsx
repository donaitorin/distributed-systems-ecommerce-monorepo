import type { Metadata } from "next";
import { requireSession } from "@ecommerce/auth/next";
import { OrderHistory } from "../../components/orders/order-history";
import { isOrderListFailure, readCursor } from "../../lib/orders";
import { LOGIN_PATH, ORDERS_PATH } from "../../lib/paths";
import { loadOrderPage } from "../../server/orders";

export const metadata: Metadata = { title: "Your orders", robots: { index: false } };

type OrdersPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function OrdersPage({ searchParams }: OrdersPageProps) {
  await requireSession({ loginPath: LOGIN_PATH });
  const cursor = readCursor((await searchParams).cursor);
  const page = await loadOrderPage(cursor);
  const retryHref = cursor ? `${ORDERS_PATH}?cursor=${encodeURIComponent(cursor)}` : ORDERS_PATH;
  return (
    <section aria-labelledby="orders-heading" className="flex flex-col gap-6">
      <h1 id="orders-heading" className="text-3xl font-semibold">
        Your orders
      </h1>
      {isOrderListFailure(page) ? (
        <div role="alert" className="flex flex-col items-start gap-3 text-base text-danger-strong">
          <p>
            {page.kind === "invalid_cursor"
              ? "This page link is no longer valid."
              : "Your orders could not be loaded right now. Try again in a moment."}
          </p>
          <a href={page.kind === "invalid_cursor" ? ORDERS_PATH : retryHref} className="text-accent-strong underline">
            {page.kind === "invalid_cursor" ? "Back to the first page" : "Try again"}
          </a>
        </div>
      ) : (
        <OrderHistory page={page} cursor={cursor} />
      )}
    </section>
  );
}
