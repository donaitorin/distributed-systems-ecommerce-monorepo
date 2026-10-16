"use client";

import { useState } from "react";
import { Button } from "@ecommerce/ui";
import { PRODUCTS_PATH } from "../../lib/paths";
import type { Category, Product } from "../../lib/types";
import { uploadProductImage, type UploadResult } from "../../lib/upload-client";
import type { DeleteResult, SaveResult, UpdateResult } from "../../server/product-actions";
import type { ProductFormValues } from "../../lib/product-form";
import { DeleteProductDialog } from "../delete-product-dialog";
import { ProductForm } from "./product-form";
import { ProductImageEditor } from "./product-image-editor";
import { useNavigation } from "../navigation";

export type ProductEditorProps = {
  categories: readonly Category[];
  initial: { product: Product; etag: string };
  updateProduct: (sku: string, etag: string, values: ProductFormValues) => Promise<UpdateResult>;
  deleteProduct: (sku: string, etag: string) => Promise<DeleteResult>;
  removeImage: (sku: string, etag: string) => Promise<SaveResult>;
  uploadImage?: (sku: string, etag: string, file: File) => Promise<UploadResult>;
};

export function ProductEditor({
  categories,
  initial,
  updateProduct,
  deleteProduct,
  removeImage,
  uploadImage = (sku, etag, file) => uploadProductImage(sku, etag, file),
}: ProductEditorProps) {
  const router = useNavigation();
  const [current, setCurrent] = useState(initial);
  const [deleting, setDeleting] = useState(false);

  const adopt = (product: Product, etag: string) => {
    setCurrent({ product, etag });
  };

  return (
    <div className="flex flex-col gap-10">
      <ProductForm
        mode="edit"
        categories={categories}
        product={current.product}
        submit={(values) => updateProduct(current.product.sku, current.etag, values)}
        onSaved={adopt}
      />
      <ProductImageEditor
        product={current.product}
        etag={current.etag}
        uploadImage={uploadImage}
        removeImage={removeImage}
        onChanged={adopt}
      />
      <section aria-labelledby="danger-heading" className="flex max-w-xl flex-col gap-3">
        <h2 id="danger-heading" className="text-xl font-semibold">
          Delete product
        </h2>
        <p className="text-sm text-secondary">
          The product is hidden from the catalog. Importing the same SKU again restores it.
        </p>
        <div>
          <Button
            variant="danger"
            onClick={() => {
              setDeleting(true);
            }}
          >
            Delete product
          </Button>
        </div>
      </section>
      <DeleteProductDialog
        product={deleting ? current.product : null}
        etag={current.etag}
        deleteProduct={deleteProduct}
        onClose={() => {
          setDeleting(false);
        }}
        onDeleted={() => {
          router.push(PRODUCTS_PATH);
        }}
      />
    </div>
  );
}
