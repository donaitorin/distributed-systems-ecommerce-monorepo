import type { Metadata } from "next";
import { ButtonLink } from "@ecommerce/ui";
import { PRODUCTS_PATH } from "../../../lib/paths";

export const metadata: Metadata = { title: "Product not found" };

export default function ProductNotFound() {
  return (
    <section aria-labelledby="not-found-heading" className="flex flex-col items-start gap-4">
      <h1 id="not-found-heading" className="text-3xl font-semibold">
        Product not found
      </h1>
      <p className="max-w-prose text-base text-secondary">
        This product does not exist or is no longer sold. Browse the catalog to find something similar.
      </p>
      <ButtonLink href={PRODUCTS_PATH}>Browse all products</ButtonLink>
    </section>
  );
}
