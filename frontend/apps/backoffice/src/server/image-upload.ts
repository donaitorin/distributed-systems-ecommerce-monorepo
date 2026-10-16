import { applyCookies, authRuntime, guardRoute } from "@ecommerce/auth/next";
import { forwardingHeaders } from "@ecommerce/auth";
import { NextResponse } from "next/server";
import { MAX_IMAGE_BYTES } from "../lib/messages";
import { REQUIRED_ROLE } from "../lib/paths";
import { streamUpload } from "./stream-upload";

const MULTIPART_OVERHEAD_BYTES = 64 * 1024;
const IMAGE_UPLOAD_TIMEOUT_MS = 60_000;

export async function putProductImage(request: Request, sku: string): Promise<Response> {
  const runtime = authRuntime();
  const guard = await guardRoute(request, { runtime, requiredRole: REQUIRED_ROLE });
  if (!guard.ok) {
    return guard.response;
  }
  const { accessToken, clientIp, cookies } = guard.access;
  const upstream = await streamUpload({
    request,
    url: `${runtime.config.apiBaseUrl}/api/v1/products/${encodeURIComponent(sku)}/image`,
    method: "PUT",
    maxBytes: MAX_IMAGE_BYTES + MULTIPART_OVERHEAD_BYTES,
    headers: { authorization: `Bearer ${accessToken}`, ...forwardingHeaders(clientIp) },
    forwardedRequestHeaders: ["content-type", "if-match"],
    timeoutMs: IMAGE_UPLOAD_TIMEOUT_MS,
  });
  return applyCookies(new NextResponse(upstream.body, upstream), cookies);
}
