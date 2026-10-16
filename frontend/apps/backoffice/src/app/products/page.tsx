import type { Metadata } from "next";
import { createLoader } from "nuqs/server";
import { ButtonLink } from "@ecommerce/ui";
import { ProductsView } from "../../components/products/products-view";
import { PRODUCTS_PATH, ZONE_PATH } from "../../lib/paths";
import { productSearchParsers } from "../../lib/product-search";
import { isFailure, loadCategories, loadProductPage } from "../../server/products";
import { deleteProductAction } from "./actions";

export const metadata: Metadata = { title: "Products" };

type ProductsPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const loadSearch = createLoader(productSearchParsers);

function toSearchParams(record: Record<string, string | string[] | undefined>): URLSearchParams {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(record)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
      search.append(name, item);
    }
  }
  return search;
}

export default async function ProductsPage({ searchParams }: ProductsPageProps) {
  const state = loadSearch(toSearchParams(await searchParams));
  const [page, categories] = await Promise.all([loadProductPage(state), loadCategories()]);
  return (
    <section aria-labelledby="products-heading" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 id="products-heading" className="text-3xl font-semibold">
          Products
        </h1>
        <div className="flex flex-wrap gap-2">
          <ButtonLink variant="secondary" href={`${ZONE_PATH}${PRODUCTS_PATH}/import`}>
            Import CSV
          </ButtonLink>
          <ButtonLink href={`${ZONE_PATH}${PRODUCTS_PATH}/new`}>New product</ButtonLink>
        </div>
      </div>
      <ProductsView
        categories={isFailure(categories) ? [] : categories}
        page={isFailure(page) ? null : page}
        failure={isFailure(page) ? page : null}
        deleteProduct={deleteProductAction}
      />
    </section>
  );
}
