import { readOrderResponse } from "../../../../server/orders";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context): Promise<Response> {
  return readOrderResponse((await params).id);
}
