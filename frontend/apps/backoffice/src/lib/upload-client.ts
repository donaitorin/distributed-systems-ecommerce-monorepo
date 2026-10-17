import { entityTag } from "./entity-tag";
import { failureFromResponse, timeoutSignal, type Failure } from "@ecommerce/web-core";
import { STREAM_PATH, ZONE_PATH } from "./paths";
import type { Product } from "./types";

export const IMAGE_UPLOAD_TIMEOUT_MS = 90_000;

export type UploadResult = { ok: true; product: Product; etag: string } | Failure;

export async function uploadProductImage(
  sku: string,
  etag: string,
  file: Blob,
  send: typeof fetch = fetch,
): Promise<UploadResult> {
  const body = new FormData();
  body.set("file", file);
  let response: Response;
  try {
    response = await send(`${ZONE_PATH}${STREAM_PATH}/products/${encodeURIComponent(sku)}/image`, {
      method: "PUT",
      headers: { "if-match": etag },
      body,
      credentials: "same-origin",
      signal: timeoutSignal(IMAGE_UPLOAD_TIMEOUT_MS),
    });
  } catch {
    return { ok: false, status: null, title: "The server could not be reached", fieldErrors: {} };
  }
  if (!response.ok) {
    return failureFromResponse(response);
  }
  const product = (await response.json()) as Product;
  return { ok: true, product, etag: response.headers.get("etag") ?? entityTag(product.version) };
}
