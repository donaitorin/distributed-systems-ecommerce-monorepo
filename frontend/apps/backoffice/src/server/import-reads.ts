import { authorizationHeaders, authRuntime } from "@ecommerce/auth/next";
import { readProblem } from "@ecommerce/api-client";
import { failureFromError, failureFromProblem, type Failure } from "@ecommerce/web-core";
import { gatewayApi } from "./gateway";
import { problemResponse } from "./stream-upload";

const IMPORT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NO_STORE = { "cache-control": "no-store" };

export function isImportId(value: string): boolean {
  return IMPORT_ID.test(value);
}

export function failureResponse(failure: Failure): Response {
  const headers = new Headers();
  if (failure.retryAfterSeconds !== undefined) {
    headers.set("retry-after", String(failure.retryAfterSeconds));
  }
  const problem = problemResponse(failure.status ?? 502, failure.title, failure.detail);
  problem.headers.forEach((value, name) => {
    headers.set(name, value);
  });
  return new Response(problem.body, { status: problem.status, headers });
}

function invalidId(): Response {
  return problemResponse(404, "Import not found", "The import id is not valid");
}

export async function readImport(id: string): Promise<Response> {
  if (!isImportId(id)) {
    return invalidId();
  }
  try {
    const { data } = await gatewayApi().get("/api/v1/imports/{import_id}", { params: { import_id: id } });
    return Response.json(data, { headers: NO_STORE });
  } catch (error) {
    return failureResponse(failureFromError(error));
  }
}

export type ProblemsQuery = { severity: string | null; cursor: string | null; limit: string | null };

export async function readProblems(id: string, { severity, cursor, limit }: ProblemsQuery): Promise<Response> {
  if (!isImportId(id)) {
    return invalidId();
  }
  const query: Record<string, string | number> = {};
  if (severity === "error" || severity === "warning") {
    query.severity = severity;
  }
  if (cursor) {
    query.cursor = cursor;
  }
  if (limit && /^\d+$/.test(limit)) {
    query.limit = Number(limit);
  }
  try {
    const { data } = await gatewayApi().get("/api/v1/imports/{import_id}/problems", {
      params: { import_id: id },
      query,
    });
    return Response.json(data, { headers: NO_STORE });
  } catch (error) {
    return failureResponse(failureFromError(error));
  }
}

export async function downloadProblemsCsv(id: string): Promise<Response> {
  if (!isImportId(id)) {
    return invalidId();
  }
  try {
    const upstream = await fetch(`${authRuntime().config.apiBaseUrl}/api/v1/imports/${id}/problems.csv`, {
      headers: await authorizationHeaders(),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return failureResponse(failureFromProblem(await readProblem(upstream)));
    }
    return new Response(upstream.body, {
      status: 200,
      headers: {
        ...NO_STORE,
        "content-type": upstream.headers.get("content-type") ?? "text/csv; charset=utf-8",
        "content-disposition": upstream.headers.get("content-disposition") ?? `attachment; filename="import-${id}-problems.csv"`,
      },
    });
  } catch {
    return failureResponse({ ok: false, status: 502, title: "The server could not be reached", fieldErrors: {} });
  }
}
