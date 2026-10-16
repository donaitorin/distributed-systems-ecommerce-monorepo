export const PROBLEM_MEDIA_TYPE = "application/problem+json";
const MEGABYTE = 1024 * 1024;
const RESPONSE_HEADERS = ["content-type", "etag", "retry-after", "x-request-id"] as const;

export type StreamUploadOptions = {
  request: Request;
  url: string;
  method: "PUT" | "POST";
  maxBytes: number;
  headers: Record<string, string>;
  forwardedRequestHeaders: readonly string[];
  timeoutMs: number;
  fetchImplementation?: typeof fetch;
};

export function problemResponse(status: number, title: string, detail?: string): Response {
  return new Response(JSON.stringify({ type: "about:blank", title, status, ...(detail ? { detail } : {}) }), {
    status,
    headers: { "content-type": PROBLEM_MEDIA_TYPE, "cache-control": "no-store" },
  });
}

function tooLarge(maxBytes: number): Response {
  return problemResponse(413, "Payload too large", `The upload exceeds the ${Math.round(maxBytes / MEGABYTE)} MB limit`);
}

function declaredLength(request: Request): number | null {
  const raw = request.headers.get("content-length");
  if (raw === null || !/^\d+$/.test(raw)) {
    return null;
  }
  return Number(raw);
}

function pick(headers: Headers): Headers {
  const picked = new Headers({ "cache-control": "no-store" });
  for (const name of RESPONSE_HEADERS) {
    const value = headers.get(name);
    if (value !== null) {
      picked.set(name, value);
    }
  }
  return picked;
}

export async function streamUpload(options: StreamUploadOptions): Promise<Response> {
  const { request, url, method, maxBytes, headers, forwardedRequestHeaders, timeoutMs } = options;
  const send = options.fetchImplementation ?? fetch;

  const declared = declaredLength(request);
  if (declared !== null && declared > maxBytes) {
    await request.body?.cancel().catch(() => undefined);
    return tooLarge(maxBytes);
  }
  if (request.body === null) {
    return problemResponse(400, "Missing request body", "A multipart form with the file is required");
  }

  let received = 0;
  let exceeded = false;
  const limiter = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      received += chunk.byteLength;
      if (received > maxBytes) {
        exceeded = true;
        controller.error(new Error("upload exceeds the limit"));
        return;
      }
      controller.enqueue(chunk);
    },
  });

  const upstreamHeaders = new Headers(headers);
  for (const name of forwardedRequestHeaders) {
    const value = request.headers.get(name);
    if (value !== null) {
      upstreamHeaders.set(name, value);
    }
  }
  if (declared !== null) {
    upstreamHeaders.set("content-length", String(declared));
  }

  try {
    const upstream = await send(url, {
      method,
      headers: upstreamHeaders,
      body: request.body.pipeThrough(limiter),
      duplex: "half",
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    } as RequestInit & { duplex: "half" });
    return new Response(upstream.body, { status: upstream.status, headers: pick(upstream.headers) });
  } catch (error) {
    if (exceeded) {
      return tooLarge(maxBytes);
    }
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return problemResponse(504, "Upload timed out", "The server took too long to accept the file");
    }
    return problemResponse(502, "The server could not be reached", "The upload could not be delivered");
  }
}
