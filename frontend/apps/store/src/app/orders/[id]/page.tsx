import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { requireSession } from "@ecommerce/auth/next";
import { OrderScreen } from "../../../components/orders/order-screen";
import { LOGIN_PATH, orderHref } from "../../../lib/paths";
import { loadOrder } from "../../../server/orders";
import { refreshCartCountAction } from "../actions";

export const metadata: Metadata = { title: "Your order", robots: { index: false } };

type PageProps = { params: Promise<{ id: string }> };

export default async function OrderPage({ params }: PageProps) {
  await requireSession({ loginPath: LOGIN_PATH });
  const { id } = await params;
  const order = await loadOrder(id);
  if ("kind" in order) {
    if (order.kind === "not_found") {
      notFound();
    }
    return (
      <section aria-labelledby="order-error-heading" className="flex flex-col gap-4">
        <h1 id="order-error-heading" className="text-3xl font-semibold">
          Your order
        </h1>
        <div role="alert" className="flex flex-col items-start gap-3 text-base text-danger-strong">
          <p>The order could not be loaded right now. It was not changed. Try again in a moment.</p>
          <a href={orderHref(id)} className="text-accent-strong underline">
            Try again
          </a>
        </div>
      </section>
    );
  }
  return <OrderScreen initial={order} onConfirmed={refreshCartCountAction} />;
}
