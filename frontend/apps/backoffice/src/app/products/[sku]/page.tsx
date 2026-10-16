import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ProductEditor } from "../../../components/products/product-editor";
import { isFailure, loadCategories, loadProduct } from "../../../server/products";
import { deleteProductAction, removeProductImageAction, updateProductAction } from "../actions";

type EditProductPageProps = {
  params: Promise<{ sku: string }>;
};

export async function generateMetadata({ params }: EditProductPageProps): Promise<Metadata> {
  const { sku } = await params;
  return { title: `Edit ${decodeURIComponent(sku)}` };
}

export default async function EditProductPage({ params }: EditProductPageProps) {
  const { sku } = await params;
  const [loaded, categories] = await Promise.all([loadProduct(decodeURIComponent(sku)), loadCategories()]);
  if (isFailure(loaded)) {
    if (loaded.status === 404) {
      notFound();
    }
    return (
      <section aria-labelledby="edit-heading" className="flex flex-col gap-4">
        <h1 id="edit-heading" className="text-3xl font-semibold">
          Edit product
        </h1>
        <p role="alert" className="max-w-prose text-base font-medium text-danger-strong">
          The product could not be loaded. Reload the page to try again.
        </p>
      </section>
    );
  }
  return (
    <section aria-labelledby="edit-heading" className="flex flex-col gap-6">
      <h1 id="edit-heading" className="text-3xl font-semibold">
        Edit product
      </h1>
      <p className="text-base text-secondary">
        {loaded.value.sku}, {loaded.value.name}
      </p>
      <ProductEditor
        categories={isFailure(categories) ? [] : categories}
        initial={{ product: loaded.value, etag: loaded.etag }}
        updateProduct={updateProductAction}
        deleteProduct={deleteProductAction}
        removeImage={removeProductImageAction}
      />
    </section>
  );
}
