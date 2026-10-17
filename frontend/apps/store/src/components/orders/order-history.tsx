import { ButtonLink, EmptyState, OrderStatusBadge } from "@ecommerce/ui";
import { formatDateTime } from "@ecommerce/web-core";
import { money, pluralItems } from "../../lib/cart";
import type { OrderPage } from "../../lib/orders";
import { orderHref, ORDERS_PATH, PRODUCTS_PATH } from "../../lib/paths";

export type OrderHistoryProps = {
  page: OrderPage;
  cursor: string | null;
};

export function nextPageHref(cursor: string): string {
  return `${ORDERS_PATH}?cursor=${encodeURIComponent(cursor)}`;
}

export function OrderHistory({ page, cursor }: OrderHistoryProps) {
  if (page.items.length === 0 && cursor === null) {
    return (
      <EmptyState
        title="You have no orders yet"
        description="When you place an order it will show up here."
        action={<ButtonLink href={PRODUCTS_PATH}>Browse products</ButtonLink>}
      />
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <ul aria-label="Your orders" className="flex flex-col gap-3">
        {page.items.map((order) => (
          <li key={order.id} className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 flex-col gap-1">
              <p className="text-base font-semibold">
                <a href={orderHref(order.id)} className="text-primary underline">
                  Order {order.id.slice(0, 8).toUpperCase()}
                </a>
              </p>
              <p className="text-sm text-secondary">
                <time dateTime={order.created_at}>{formatDateTime(order.created_at)}</time>
              </p>
              <p className="text-sm text-secondary">{pluralItems(order.item_count)}</p>
            </div>
            <div className="flex items-center justify-between gap-4 sm:flex-col sm:items-end sm:gap-2">
              <OrderStatusBadge status={order.status} />
              <p className="text-base font-semibold">
                <span className="sr-only">Total: </span>
                {money(order.total)}
              </p>
            </div>
          </li>
        ))}
      </ul>
      {cursor !== null || page.next_cursor !== null ? (
        <nav aria-label="Order pages" className="flex flex-wrap items-center gap-3">
          {cursor !== null ? (
            <ButtonLink href={ORDERS_PATH} variant="secondary">
              First page
            </ButtonLink>
          ) : null}
          {page.next_cursor !== null ? (
            <ButtonLink href={nextPageHref(page.next_cursor)} variant="secondary">
              Next page
            </ButtonLink>
          ) : null}
        </nav>
      ) : null}
    </div>
  );
}
