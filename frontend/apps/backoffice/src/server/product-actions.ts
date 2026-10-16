import { ApiError } from "@ecommerce/api-client";
import { entityTag } from "../lib/entity-tag";
import { failureFromError, type Failure } from "../lib/failure";
import { apiFieldName, productFormSchema, toCreateBody, toWriteBody, type ProductField, type ProductFormValues } from "../lib/product-form";
import type { Product, WithEtag } from "../lib/types";
import { catalogApi } from "./catalog";
import { guarded } from "./guarded";

export type Saved = { ok: true; product: Product; etag: string };
export type Removed = { ok: true };
export type ConflictFailure = Failure & { latest?: WithEtag<Product> };
export type SaveResult = Saved | Failure;
export type UpdateResult = Saved | ConflictFailure;
export type DeleteResult = Removed | Failure;

const PRECONDITION_FAILED = 412;
const UNPROCESSABLE = 422;

function savedFrom(product: Product, response: Response): Saved {
  return { ok: true, product, etag: response.headers.get("etag") ?? entityTag(product.version) };
}

function invalidFailure(error: { issues: readonly { path: PropertyKey[]; message: string }[] }): Failure {
  const fieldErrors: Record<string, string> = {};
  for (const issue of error.issues) {
    const field = issue.path[0];
    if (typeof field === "string") {
      const apiName = apiFieldName(field as ProductField);
      fieldErrors[apiName] ??= issue.message;
    }
  }
  return { ok: false, status: UNPROCESSABLE, title: "Validation failed", fieldErrors };
}

export async function createProduct(values: ProductFormValues): Promise<SaveResult> {
  const parsed = productFormSchema.safeParse(values);
  if (!parsed.success) {
    return invalidFailure(parsed.error);
  }
  return guarded(async () => {
    const { data, response } = await catalogApi().post("/api/v1/products", { body: toCreateBody(parsed.data) });
    return savedFrom(data, response);
  });
}

async function latestOf(sku: string): Promise<WithEtag<Product> | undefined> {
  try {
    const { data, response } = await catalogApi().get("/api/v1/products/{sku}", { params: { sku } });
    return { value: data, etag: response.headers.get("etag") ?? entityTag(data.version) };
  } catch {
    return undefined;
  }
}

export async function updateProduct(sku: string, etag: string, values: ProductFormValues): Promise<UpdateResult> {
  const parsed = productFormSchema.safeParse(values);
  if (!parsed.success) {
    return invalidFailure(parsed.error);
  }
  return guarded<Saved | ConflictFailure>(async () => {
    try {
      const { data, response } = await catalogApi().put("/api/v1/products/{sku}", {
        params: { sku },
        headers: { "if-match": etag },
        body: toWriteBody(parsed.data),
      });
      return savedFrom(data, response);
    } catch (error) {
      if (error instanceof ApiError && error.status === PRECONDITION_FAILED) {
        const latest = await latestOf(sku);
        return { ...failureFromError(error), ...(latest ? { latest } : {}) };
      }
      throw error;
    }
  });
}

export async function deleteProduct(sku: string, etag: string): Promise<DeleteResult> {
  return guarded(async () => {
    await catalogApi().delete("/api/v1/products/{sku}", { params: { sku }, headers: { "if-match": etag } });
    return { ok: true as const };
  });
}

export async function removeProductImage(sku: string, etag: string): Promise<SaveResult> {
  return guarded(async () => {
    const { data, response } = await catalogApi().delete("/api/v1/products/{sku}/image", {
      params: { sku },
      headers: { "if-match": etag },
    });
    return savedFrom(data, response);
  });
}
