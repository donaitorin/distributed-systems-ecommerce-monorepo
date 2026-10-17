import { ButtonLink } from "@ecommerce/ui";
import { PRODUCTS_PATH } from "../../../lib/paths";

export default function OrderNotFound() {
  return (
    <section aria-labelledby="order-missing-heading" className="flex flex-col items-start gap-4">
      <h1 id="order-missing-heading" className="text-3xl font-semibold">
        Order not found
      </h1>
      <p className="text-base text-secondary">We could not find this order in your account.</p>
      <ButtonLink href={PRODUCTS_PATH}>Browse products</ButtonLink>
    </section>
  );
}
