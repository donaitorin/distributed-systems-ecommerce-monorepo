import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import ProductPage, { generateMetadata } from "../src/app/products/[sku]/page";
import ProductNotFound from "../src/app/products/[sku]/not-found";
import { product } from "./support/api";

const loadProduct = jest.fn();

jest.mock("../src/server/catalog", () => ({
  loadProduct: (sku: string) => loadProduct(sku) as unknown,
}));

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const FAILURE = { ok: false, status: 503, title: "Down", fieldErrors: {} };
const NOT_FOUND = { ok: false, status: 404, title: "Product not found", fieldErrors: {} };
const params = (sku: string) => Promise.resolve({ sku });

beforeEach(() => {
  loadProduct.mockReset();
  loadProduct.mockResolvedValue(product());
});

describe("product page", () => {
  it("renders the product", async () => {
    const { container } = render(await ProductPage({ params: params("RS-001") }));

    expect(screen.getByRole("heading", { level: 1, name: "Running shoes" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("asks the API with the decoded SKU", async () => {
    loadProduct.mockResolvedValue(product({ sku: "RS 001" }));

    await ProductPage({ params: params("RS%20001") });

    expect(loadProduct).toHaveBeenCalledWith("RS 001");
  });

  it("redirects a SKU in another case to the canonical address", async () => {
    await expect(ProductPage({ params: params("rs-001") })).rejects.toThrow("NEXT_REDIRECT /products/RS-001");
  });

  it("is a 404 for an unknown or retired product", async () => {
    loadProduct.mockResolvedValue(NOT_FOUND);

    await expect(ProductPage({ params: params("NOPE-1") })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("is a 404 for a malformed address", async () => {
    await expect(ProductPage({ params: params("%E0%A4%A") })).rejects.toThrow("NEXT_NOT_FOUND");
    expect(loadProduct).not.toHaveBeenCalled();
  });

  it("explains a temporary failure with a way to retry instead of a 404", async () => {
    loadProduct.mockResolvedValue(FAILURE);

    const { container } = render(await ProductPage({ params: params("RS-001") }));

    expect(screen.getByRole("heading", { level: 1, name: "Product unavailable" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/products/RS-001");
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("product page metadata", () => {
  it("uses the product name, a summary and the canonical address", async () => {
    expect(await generateMetadata({ params: params("rs-001") })).toMatchObject({
      title: "Running shoes",
      description: "Light and fast",
      alternates: { canonical: "/products/RS-001" },
      openGraph: { title: "Running shoes" },
    });
  });

  it("shortens long descriptions and falls back to the price without one", async () => {
    loadProduct.mockResolvedValue(product({ description: `${"word ".repeat(60)}end` }));
    const long = await generateMetadata({ params: params("RS-001") });
    loadProduct.mockResolvedValue(product({ description: null }));
    const none = await generateMetadata({ params: params("RS-001") });

    expect((long.description ?? "").length).toBeLessThanOrEqual(160);
    expect(long.description).toMatch(/…$/);
    expect(none.description).toBe("Running shoes at $59.00.");
  });

  it("is not indexed when the product could not be loaded", async () => {
    loadProduct.mockResolvedValue(FAILURE);

    expect(await generateMetadata({ params: params("RS-001") })).toMatchObject({ robots: { index: false } });
  });
});

describe("product not found page", () => {
  it("has one heading and a way back to the catalog", async () => {
    const { container } = render(<ProductNotFound />);

    expect(screen.getByRole("heading", { level: 1, name: "Product not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse all products" })).toHaveAttribute("href", "/products");
    expect(await axe(container)).toHaveNoViolations();
  });
});
