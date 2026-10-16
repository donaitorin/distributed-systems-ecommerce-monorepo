import type { Metadata } from "next";
import { ProductForm } from "../../../components/products/product-form";
import { isFailure, loadCategories } from "../../../server/products";
import { createProductAction } from "../actions";

export const metadata: Metadata = { title: "New product" };

export default async function NewProductPage() {
  const categories = await loadCategories();
  return (
    <section aria-labelledby="new-product-heading" className="flex flex-col gap-6">
      <h1 id="new-product-heading" className="text-3xl font-semibold">
        New product
      </h1>
      {isFailure(categories) ? (
        <p role="alert" className="max-w-prose text-sm font-medium text-danger-strong">
          The categories could not be loaded, so the category list is empty. Reload the page to try again.
        </p>
      ) : null}
      <ProductForm
        mode="create"
        categories={isFailure(categories) ? [] : categories}
        submit={createProductAction}
      />
    </section>
  );
}
