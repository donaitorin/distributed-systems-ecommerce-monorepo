import type { Metadata } from "next";
import { createLoader } from "nuqs/server";
import { OrdersView } from "../../components/orders/orders-view";
import { dateRangeError, orderSearchParsers } from "../../lib/order-search";
import { loadOrderPage } from "../../server/orders";
import { isFailure } from "../../server/products";

export const metadata: Metadata = { title: "Orders" };

type OrdersPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const loadSearch = createLoader(orderSearchParsers);

function toSearchParams(record: Record<string, string | string[] | undefined>): URLSearchParams {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(record)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
      search.append(name, item);
    }
  }
  return search;
}

export default async function OrdersPage({ searchParams }: OrdersPageProps) {
  const state = loadSearch(toSearchParams(await searchParams));
  const page = dateRangeError(state) === null ? await loadOrderPage(state) : null;
  return (
    <section aria-labelledby="orders-heading" className="flex flex-col gap-6">
      <h1 id="orders-heading" className="text-3xl font-semibold">
        Orders
      </h1>
      <OrdersView page={page === null || isFailure(page) ? null : page} failure={page !== null && isFailure(page) ? page : null} />
    </section>
  );
}
