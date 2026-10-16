import { readProblems } from "../../../../../server/import-reads";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, { params }: Context): Promise<Response> {
  const search = new URL(request.url).searchParams;
  return readProblems((await params).id, {
    severity: search.get("severity"),
    cursor: search.get("cursor"),
    limit: search.get("limit"),
  });
}
