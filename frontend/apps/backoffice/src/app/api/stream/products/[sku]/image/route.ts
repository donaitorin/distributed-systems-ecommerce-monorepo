import { putProductImage } from "../../../../../../server/image-upload";

export const runtime = "nodejs";

type Context = { params: Promise<{ sku: string }> };

export async function PUT(request: Request, { params }: Context): Promise<Response> {
  const { sku } = await params;
  return putProductImage(request, sku);
}
