import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isFailure } from "@ecommerce/web-core";
import { OrderDetailView } from "../../../components/orders/order-detail-view";
import { shortOrderId } from "../../../lib/order-format";
import { loadOrder } from "../../../server/orders";

type OrderPageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: OrderPageProps): Promise<Metadata> {
  const { id } = await params;
  return { title: `Order ${shortOrderId(id)}` };
}

export default async function OrderPage({ params }: OrderPageProps) {
  const { id } = await params;
  const loaded = await loadOrder(id);
  if (isFailure(loaded)) {
    if (loaded.status === 404) {
      notFound();
    }
    return (
      <section aria-labelledby="order-heading" className="flex flex-col gap-4">
        <h1 id="order-heading" className="text-3xl font-semibold">
          Order {shortOrderId(id)}
        </h1>
        <p role="alert" className="max-w-prose text-base font-medium text-danger-strong">
          The order could not be loaded. Reload the page to try again.
        </p>
      </section>
    );
  }
  return (
    <section aria-labelledby="order-heading" className="flex flex-col gap-6">
      <h1 id="order-heading" className="text-3xl font-semibold">
        Order {shortOrderId(id)}
      </h1>
      <OrderDetailView order={loaded.order} payment={loaded.payment} />
    </section>
  );
}
