import { ApiError, ApiNetworkError, readProblem } from "./problem";
import type {
  ApiResult,
  HttpMethod,
  OperationOf,
  OptionsArguments,
  PathsWith,
  ResponseBody,
} from "./types";

export type ApiClientOptions = {
  baseUrl: string;
  fetch?: typeof fetch;
  headers?: () => Record<string, string> | Promise<Record<string, string>>;
  timeoutMs?: number;
};

type LooseOptions = {
  query?: Record<string, unknown>;
  params?: Record<string, unknown>;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
};

const DEFAULT_TIMEOUT_MS = 10_000;
const NO_CONTENT = 204;

function scalar(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function buildQuery(query: Record<string, unknown> | undefined): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    for (const item of Array.isArray(value) ? (value as unknown[]) : [value]) {
      if (item !== undefined && item !== null) {
        search.append(key, scalar(item));
      }
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function buildPath(template: string, params: Record<string, unknown> | undefined): string {
  return template.replace(/\{([^}]+)\}/g, (_match, name: string) => {
    const value = params?.[name];
    if (value === undefined || value === null) {
      throw new Error(`Missing path parameter "${name}" for ${template}`);
    }
    return encodeURIComponent(scalar(value));
  });
}

function requestBody(body: unknown): { body?: BodyInit; contentType?: string } {
  if (body === undefined) {
    return {};
  }
  if (body instanceof FormData) {
    return { body };
  }
  return { body: JSON.stringify(body), contentType: "application/json" };
}

function combineSignals(
  signal: AbortSignal | undefined,
  timeoutMs: number,
): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export function createApiClient<Paths>(clientOptions: ApiClientOptions) {
  const baseUrl = clientOptions.baseUrl.replace(/\/+$/, "");
  const doFetch = clientOptions.fetch ?? fetch;

  async function request(
    method: HttpMethod,
    template: string,
    options: LooseOptions,
  ): Promise<{ data: unknown; response: Response }> {
    const url = `${baseUrl}${buildPath(template, options.params)}${buildQuery(options.query)}`;
    const payload = requestBody(options.body);
    const defaults = (await clientOptions.headers?.()) ?? {};
    const headers: Record<string, string> = {
      accept: "application/json, application/problem+json",
      ...defaults,
      ...(payload.contentType ? { "content-type": payload.contentType } : {}),
      ...options.headers,
    };

    let response: Response;
    try {
      response = await doFetch(url, {
        method: method.toUpperCase(),
        headers,
        body: payload.body,
        signal: combineSignals(options.signal, options.timeoutMs ?? clientOptions.timeoutMs ?? DEFAULT_TIMEOUT_MS),
        cache: "no-store",
      });
    } catch (error) {
      if (options.signal?.aborted) {
        throw error;
      }
      throw new ApiNetworkError(error);
    }

    if (!response.ok) {
      throw new ApiError(await readProblem(response), response);
    }
    if (response.status === NO_CONTENT) {
      return { data: undefined, response };
    }
    return { data: await response.json(), response };
  }

  function bind<Method extends HttpMethod>(method: Method) {
    return async <Path extends PathsWith<Paths, Method>>(
      path: Path,
      ...args: OptionsArguments<OperationOf<Paths, Path, Method>>
    ): Promise<ApiResult<OperationOf<Paths, Path, Method>>> => {
      const result = await request(method, path, (args[0] ?? {}) as LooseOptions);
      return result as { data: ResponseBody<OperationOf<Paths, Path, Method>>; response: Response };
    };
  }

  return {
    get: bind("get"),
    post: bind("post"),
    put: bind("put"),
    patch: bind("patch"),
    delete: bind("delete"),
  };
}

export type ApiClient<Paths> = ReturnType<typeof createApiClient<Paths>>;
