import type { Metadata } from "next";
import {
  hasActiveFilters,
  isFailure,
  loadProductSearch,
  type SearchParamsRecord,
} from "@ecommerce/web-core";
import { ProductSearch } from "../../components/catalog/product-search";
import { loadCategories, loadProductPage } from "../../server/catalog";

type ProductsPageProps = {
  searchParams: Promise<SearchParamsRecord>;
};

export async function generateMetadata({ searchParams }: ProductsPageProps): Promise<Metadata> {
  const state = loadProductSearch(await searchParams);
  const searching = state.q !== null;
  return {
    title: searching ? `Results for "${state.q}"` : "Products",
    description: "Browse and search the catalog.",
    robots: hasActiveFilters(state) || state.cursor !== null ? { index: false, follow: true } : undefined,
  };
}

export default async function ProductsPage({ searchParams }: ProductsPageProps) {
  const state = loadProductSearch(await searchParams);
  const [page, categories] = await Promise.all([loadProductPage(state), loadCategories()]);
  return (
    <section aria-labelledby="products-heading" className="flex flex-col gap-6">
      <h1 id="products-heading" className="text-3xl font-semibold">
        {state.q ? `Results for "${state.q}"` : "Products"}
      </h1>
      <ProductSearch
        categories={isFailure(categories) ? [] : categories}
        page={isFailure(page) ? null : page}
        failure={isFailure(page) ? page : null}
      />
    </section>
  );
}
