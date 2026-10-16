import { failureFromResponse, type Failure } from "./failure";
import { STREAM_PATH, ZONE_PATH } from "./paths";
import type { ImportProblemsPage, ImportView } from "./types";

export type Fetch = typeof fetch;
export type Loaded<Value> = ({ ok: true } & Value) | Failure;

const SESSION_EXPIRED: Failure = { ok: false, status: 401, title: "Your session expired", fieldErrors: {} };
const UNREACHABLE: Failure = { ok: false, status: null, title: "The server could not be reached", fieldErrors: {} };

async function request(url: string, init: RequestInit, send: Fetch): Promise<Response | Failure> {
  let response: Response;
  try {
    response = await send(url, { ...init, credentials: "same-origin", redirect: "manual" });
  } catch {
    return UNREACHABLE;
  }
  if (response.type === "opaqueredirect") {
    return SESSION_EXPIRED;
  }
  return response.ok ? response : failureFromResponse(response);
}

function isFailure(value: Response | Failure): value is Failure {
  return "fieldErrors" in value;
}

export function importUrl(importId: string): string {
  return `${ZONE_PATH}/api/imports/${encodeURIComponent(importId)}`;
}

export function problemsCsvUrl(importId: string): string {
  return `${importUrl(importId)}/problems.csv`;
}

export async function uploadImportFile(file: Blob, send: Fetch = fetch): Promise<Loaded<{ import: ImportView; existing: boolean }>> {
  const body = new FormData();
  body.set("file", file);
  const response = await request(`${ZONE_PATH}${STREAM_PATH}/imports`, { method: "POST", body }, send);
  if (isFailure(response)) {
    return response;
  }
  return { ok: true, import: (await response.json()) as ImportView, existing: response.status === 200 };
}

export async function fetchImport(importId: string, send: Fetch = fetch): Promise<Loaded<{ import: ImportView }>> {
  const response = await request(importUrl(importId), { method: "GET", headers: { accept: "application/json" } }, send);
  return isFailure(response) ? response : { ok: true, import: (await response.json()) as ImportView };
}

export type ProblemsRequest = { severity: "error" | "warning" | null; cursor: string | null; limit?: number };

export async function fetchProblems(
  importId: string,
  { severity, cursor, limit = 50 }: ProblemsRequest,
  send: Fetch = fetch,
): Promise<Loaded<{ page: ImportProblemsPage }>> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (severity) {
    query.set("severity", severity);
  }
  if (cursor) {
    query.set("cursor", cursor);
  }
  const response = await request(`${importUrl(importId)}/problems?${query.toString()}`, { method: "GET" }, send);
  return isFailure(response) ? response : { ok: true, page: (await response.json()) as ImportProblemsPage };
}

export class ImportRequestError extends Error {
  readonly failure: Failure;

  constructor(failure: Failure) {
    super(failure.title);
    this.name = "ImportRequestError";
    this.failure = failure;
  }
}

export function unwrap<Value extends object>(result: Loaded<Value>): { ok: true } & Value {
  if (!result.ok) {
    throw new ImportRequestError(result);
  }
  return result;
}


