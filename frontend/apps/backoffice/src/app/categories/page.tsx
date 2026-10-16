import type { Metadata } from "next";
import { CategoriesView } from "../../components/categories/categories-view";
import { isFailure, loadCategories } from "../../server/products";
import { createCategoryAction } from "./actions";

export const metadata: Metadata = { title: "Categories" };

export default async function CategoriesPage() {
  const categories = await loadCategories();
  return (
    <section aria-labelledby="categories-heading" className="flex flex-col gap-6">
      <h1 id="categories-heading" className="text-3xl font-semibold">
        Categories
      </h1>
      <CategoriesView
        categories={isFailure(categories) ? [] : categories}
        failure={isFailure(categories) ? categories : null}
        createCategory={createCategoryAction}
      />
    </section>
  );
}
