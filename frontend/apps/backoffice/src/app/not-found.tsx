import { ButtonLink } from "@ecommerce/ui";
import { PRODUCTS_PATH, ZONE_PATH } from "../lib/paths";

export default function NotFound() {
  return (
    <section aria-labelledby="not-found-heading" className="flex flex-col items-start gap-4">
      <h1 id="not-found-heading" className="text-3xl font-semibold">
        Page not found
      </h1>
      <p className="max-w-prose text-base text-secondary">
        This page, product or order does not exist, or it was removed.
      </p>
      <ButtonLink href={`${ZONE_PATH}${PRODUCTS_PATH}`}>Back to products</ButtonLink>
    </section>
  );
}
