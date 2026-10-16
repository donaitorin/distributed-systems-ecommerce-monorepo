"use server";

import type { ProductFormValues } from "../../lib/product-form";
import {
  createProduct,
  deleteProduct,
  removeProductImage,
  updateProduct,
  type DeleteResult,
  type SaveResult,
  type UpdateResult,
} from "../../server/product-actions";

export async function createProductAction(values: ProductFormValues): Promise<SaveResult> {
  return createProduct(values);
}

export async function updateProductAction(sku: string, etag: string, values: ProductFormValues): Promise<UpdateResult> {
  return updateProduct(sku, etag, values);
}

export async function deleteProductAction(sku: string, etag: string): Promise<DeleteResult> {
  return deleteProduct(sku, etag);
}

export async function removeProductImageAction(sku: string, etag: string): Promise<SaveResult> {
  return removeProductImage(sku, etag);
}
