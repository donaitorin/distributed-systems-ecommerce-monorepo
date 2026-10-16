import { applyCookies, authRuntime, guardRoute } from "@ecommerce/auth/next";
import { forwardingHeaders } from "@ecommerce/auth";
import { NextResponse } from "next/server";
import { REQUIRED_ROLE } from "../lib/paths";
import { importMaxBytes } from "./import-config";
import { streamUpload } from "./stream-upload";

export const MULTIPART_OVERHEAD_BYTES = 64 * 1024;
const IMPORT_UPLOAD_TIMEOUT_MS = 15 * 60 * 1000;

export async function postImport(request: Request): Promise<Response> {
  const runtime = authRuntime();
  const guard = await guardRoute(request, { runtime, requiredRole: REQUIRED_ROLE });
  if (!guard.ok) {
    return guard.response;
  }
  const { accessToken, clientIp, cookies } = guard.access;
  const upstream = await streamUpload({
    request,
    url: `${runtime.config.apiBaseUrl}/api/v1/imports`,
    method: "POST",
    maxBytes: importMaxBytes() + MULTIPART_OVERHEAD_BYTES,
    headers: { authorization: `Bearer ${accessToken}`, ...forwardingHeaders(clientIp) },
    forwardedRequestHeaders: ["content-type"],
    timeoutMs: IMPORT_UPLOAD_TIMEOUT_MS,
  });
  return applyCookies(new NextResponse(upstream.body, upstream), cookies);
}
