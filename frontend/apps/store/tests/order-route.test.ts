/**
 * @jest-environment node
 */
import { GET } from "../src/app/api/orders/[id]/route";

const readOrderResponse = jest.fn();

jest.mock("../src/server/orders", () => ({ readOrderResponse: (id: string) => readOrderResponse(id) as unknown }));

describe("GET /api/orders/{id}", () => {
  it("answers with what the server module read for that order", async () => {
    readOrderResponse.mockResolvedValue(Response.json({ id: "o1" }));

    const response = await GET(new Request("http://store.test/api/orders/o1"), { params: Promise.resolve({ id: "o1" }) });

    expect(readOrderResponse).toHaveBeenCalledWith("o1");
    expect(await response.json()).toEqual({ id: "o1" });
  });
});
