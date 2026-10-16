import { downloadProblemsCsv } from "../../../../../server/import-reads";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context): Promise<Response> {
  return downloadProblemsCsv((await params).id);
}
