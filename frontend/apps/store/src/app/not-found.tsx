import type { Metadata } from "next";
import { ButtonLink } from "@ecommerce/ui";
import { PRODUCTS_PATH } from "../lib/paths";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <section aria-labelledby="not-found-heading" className="flex flex-col items-start gap-4">
      <h1 id="not-found-heading" className="text-3xl font-semibold">
        Page not found
      </h1>
      <p className="max-w-prose text-base text-secondary">
        This page does not exist, or it was moved. Browse the catalog to find what you need.
      </p>
      <ButtonLink href={PRODUCTS_PATH}>Back to products</ButtonLink>
    </section>
  );
}
