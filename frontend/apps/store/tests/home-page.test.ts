/**
 * @jest-environment node
 */
import HomePage from "../src/app/page";

const redirect = jest.fn();

jest.mock("next/navigation", () => ({
  redirect: (path: string) => {
    redirect(path);
    throw new Error(`NEXT_REDIRECT ${path}`);
  },
}));

beforeEach(() => {
  redirect.mockReset();
});

describe("home page", () => {
  it("sends visitors to the product search", async () => {
    await expect(HomePage({ searchParams: Promise.resolve({}) })).rejects.toThrow("NEXT_REDIRECT /products");

    expect(redirect).toHaveBeenCalledWith("/products");
  });

  it("keeps the query string, including repeated and encoded values", async () => {
    await expect(
      HomePage({ searchParams: Promise.resolve({ q: "running shoes", in_stock: "true", tag: ["a", "b"] }) }),
    ).rejects.toThrow("NEXT_REDIRECT");

    expect(redirect).toHaveBeenCalledWith("/products?q=running+shoes&in_stock=true&tag=a&tag=b");
  });
});
