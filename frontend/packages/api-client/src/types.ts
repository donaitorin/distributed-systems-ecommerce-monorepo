export type HttpMethod = "get" | "post" | "put" | "patch" | "delete";

export type PathsWith<Paths, Method extends HttpMethod> = {
  [Path in keyof Paths]: Paths[Path] extends { [Key in Method]: object } ? Path : never;
}[keyof Paths] &
  string;

export type OperationOf<
  Paths,
  Path extends keyof Paths,
  Method extends HttpMethod,
> = Paths[Path] extends { [Key in Method]: infer Operation } ? Operation : never;

type QueryOf<Operation> = Operation extends { parameters: { query?: infer Query } }
  ? Exclude<Query, undefined>
  : never;

type PathParamsOf<Operation> = Operation extends { parameters: { path?: infer Params } }
  ? Exclude<Params, undefined>
  : never;

type QueryOption<Operation> = [QueryOf<Operation>] extends [never]
  ? { query?: undefined }
  : { query?: QueryOf<Operation> };

type PathOption<Operation> = [PathParamsOf<Operation>] extends [never]
  ? { params?: undefined }
  : { params: PathParamsOf<Operation> };

type BodyOption<Operation> = Operation extends {
  requestBody: { content: { "application/json": infer Body } };
}
  ? { body: Body }
  : Operation extends { requestBody?: { content: { "application/json": infer Body } } }
    ? { body?: Body }
    : Operation extends { requestBody: { content: { "multipart/form-data": unknown } } }
      ? { body: FormData }
      : { body?: undefined };

export type RequestOptions<Operation> = QueryOption<Operation> &
  PathOption<Operation> &
  BodyOption<Operation> & {
    headers?: Record<string, string>;
    signal?: AbortSignal;
    timeoutMs?: number;
  };

export type OptionsArguments<Operation> = object extends RequestOptions<Operation>
  ? [options?: RequestOptions<Operation>]
  : [options: RequestOptions<Operation>];

type SuccessStatus = 200 | 201 | 202 | 203 | 204 | 205 | 206;

export type ResponseBody<Operation> = Operation extends { responses: infer Responses }
  ? {
      [Status in keyof Responses & SuccessStatus]: Responses[Status] extends {
        content: { "application/json": infer Body };
      }
        ? Body
        : undefined;
    }[keyof Responses & SuccessStatus]
  : unknown;

export type ApiResult<Operation> = {
  data: ResponseBody<Operation>;
  response: Response;
};
