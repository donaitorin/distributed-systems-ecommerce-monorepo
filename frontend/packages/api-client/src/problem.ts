export type FieldError = {
  location: string;
  message: string;
  type: string;
};

export type ProblemDetails = {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  request_id?: string;
  errors?: FieldError[];
  [extension: string]: unknown;
};

export const PROBLEM_MEDIA_TYPE = "application/problem+json";

const SNIPPET_LENGTH = 200;

function isProblem(value: unknown): value is ProblemDetails {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).title === "string" &&
    typeof (value as Record<string, unknown>).status === "number"
  );
}

function fallbackProblem(response: Response, text: string): ProblemDetails {
  const snippet = text.trim().slice(0, SNIPPET_LENGTH);
  return {
    type: "about:blank",
    title: response.statusText || `HTTP ${response.status}`,
    status: response.status,
    ...(snippet ? { detail: snippet } : {}),
  };
}

export async function readProblem(response: Response): Promise<ProblemDetails> {
  const text = await response.text().catch(() => "");
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes(PROBLEM_MEDIA_TYPE)) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (isProblem(parsed)) {
        return parsed;
      }
    } catch {
      return fallbackProblem(response, text);
    }
  }
  return fallbackProblem(response, text);
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails;
  readonly response: Response;

  constructor(problem: ProblemDetails, response: Response) {
    super(problem.detail ? `${problem.title}: ${problem.detail}` : problem.title);
    this.name = "ApiError";
    this.status = problem.status;
    this.problem = problem;
    this.response = response;
  }

  get requestId(): string | undefined {
    return this.problem.request_id ?? this.response.headers.get("x-request-id") ?? undefined;
  }

  get retryAfterSeconds(): number | undefined {
    const value = Number(this.response.headers.get("retry-after"));
    return Number.isFinite(value) && value > 0 ? value : undefined;
  }

  fieldErrors(): FieldError[] {
    return this.problem.errors ?? [];
  }
}

export class ApiNetworkError extends Error {
  constructor(cause: unknown) {
    super("The API could not be reached", { cause });
    this.name = "ApiNetworkError";
  }
}
