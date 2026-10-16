import { ApiError, ApiNetworkError, readProblem, type ProblemDetails } from "@ecommerce/api-client";

export type Failure = {
  ok: false;
  status: number | null;
  title: string;
  detail?: string;
  fieldErrors: Record<string, string>;
  retryAfterSeconds?: number;
};

const FIELD_LOCATION = /^(?:body|query)\.(.+)$/;
const NETWORK_TITLE = "The server could not be reached";

function fieldErrorsOf(problem: ProblemDetails): Record<string, string> {
  const result: Record<string, string> = {};
  for (const { location, message } of problem.errors ?? []) {
    const field = FIELD_LOCATION.exec(location)?.[1];
    if (field !== undefined && !(field in result)) {
      result[field] = message;
    }
  }
  return result;
}

export function failureFromProblem(problem: ProblemDetails, retryAfterSeconds?: number): Failure {
  return {
    ok: false,
    status: problem.status,
    title: problem.title,
    ...(problem.detail ? { detail: problem.detail } : {}),
    fieldErrors: fieldErrorsOf(problem),
    ...(retryAfterSeconds !== undefined ? { retryAfterSeconds } : {}),
  };
}

export function failureFromError(error: unknown): Failure {
  if (error instanceof ApiError) {
    return failureFromProblem(error.problem, error.retryAfterSeconds);
  }
  if (error instanceof ApiNetworkError) {
    return { ok: false, status: null, title: NETWORK_TITLE, fieldErrors: {} };
  }
  throw error;
}

export async function failureFromResponse(response: Response): Promise<Failure> {
  const retryAfter = Number(response.headers.get("retry-after"));
  return failureFromProblem(
    await readProblem(response),
    Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
  );
}

export function isSessionFailure(failure: Failure): boolean {
  return failure.status === 401 || failure.status === 403;
}
