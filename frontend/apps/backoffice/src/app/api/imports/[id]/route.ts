import { readImport } from "../../../../server/import-reads";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context): Promise<Response> {
  return readImport((await params).id);
}
