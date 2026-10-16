"use client";

import { useState } from "react";
import { ConfirmDialog } from "@ecommerce/ui";
import { entityTag } from "../lib/entity-tag";
import { isSessionFailure } from "../lib/failure";
import { LOGIN_PATH } from "../lib/paths";
import { deleteFailureMessage } from "../lib/messages";
import type { Product } from "../lib/types";
import type { DeleteResult } from "../server/product-actions";
import { useNotify } from "./notifications";
import { useNavigation } from "./navigation";

export type DeleteTarget = Pick<Product, "sku" | "name" | "version">;

export type DeleteProductDialogProps = {
  product: DeleteTarget | null;
  etag?: string;
  deleteProduct: (sku: string, etag: string) => Promise<DeleteResult>;
  onClose: () => void;
  onDeleted: () => void;
};

export function DeleteProductDialog({ product, etag, deleteProduct, onClose, onDeleted }: DeleteProductDialogProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const notify = useNotify();
  const router = useNavigation();

  const close = () => {
    setError(undefined);
    onClose();
  };

  const confirm = async () => {
    if (!product) {
      return;
    }
    setPending(true);
    const result = await deleteProduct(product.sku, etag ?? entityTag(product.version));
    setPending(false);
    if (result.ok) {
      setError(undefined);
      notify({ title: "Product deleted", description: `${product.sku} was removed from the catalog.`, variant: "success" });
      onDeleted();
      return;
    }
    if (isSessionFailure(result)) {
      router.push(`${LOGIN_PATH}?reason=expired`);
      return;
    }
    const message = deleteFailureMessage(result);
    setError(message);
    notify({ title: "Could not delete the product", description: message, variant: "error" });
  };

  return (
    <ConfirmDialog
      open={product !== null}
      onOpenChange={(open) => {
        if (!open) {
          close();
        }
      }}
      title="Delete this product?"
      description={
        product
          ? `${product.sku}, ${product.name}, will be hidden from the catalog. Importing the same SKU again restores it.`
          : undefined
      }
      confirmLabel="Delete product"
      variant="danger"
      pending={pending}
      error={error}
      onConfirm={() => {
        void confirm();
      }}
    />
  );
}
