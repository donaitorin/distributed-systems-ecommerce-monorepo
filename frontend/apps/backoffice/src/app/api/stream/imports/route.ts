import { postImport } from "../../../../server/import-upload";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return postImport(request);
}
