import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import ProductsPage, { generateMetadata } from "../src/app/products/page";
import { CATEGORY, productPage } from "./support/api";

const loadProductPage = jest.fn();
const loadCategories = jest.fn();

jest.mock("../src/server/catalog", () => ({
  loadProductPage: (...args: unknown[]) => loadProductPage(...args) as unknown,
  loadCategories: () => loadCategories() as unknown,
}));

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const FAILURE = { ok: false, status: 503, title: "Down", fieldErrors: {} };

function inProviders(element: React.ReactElement) {
  return render(<NuqsTestingAdapter>{element}</NuqsTestingAdapter>);
}

beforeEach(() => {
  loadProductPage.mockReset();
  loadCategories.mockReset();
  loadCategories.mockResolvedValue([CATEGORY]);
  loadProductPage.mockResolvedValue(productPage());
});

describe("products page", () => {
  it("renders the first results on the server for the URL's search, ignoring invalid values", async () => {
    const { container } = inProviders(
      await ProductsPage({ searchParams: Promise.resolve({ q: "shoes", limit: "48", min_price: "abc" }) }),
    );

    expect(loadProductPage).toHaveBeenCalledWith(expect.objectContaining({ q: "shoes", limit: 48, min_price: null }));
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent('Results for "shoes"');
    expect(screen.getByRole("link", { name: "Running shoes" })).toHaveAttribute("href", "/products/RS-001");
    expect(screen.getByRole("status")).toHaveTextContent("2 results");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("titles an unfiltered search 'Products'", async () => {
    inProviders(await ProductsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("heading", { level: 1, name: "Products" })).toBeInTheDocument();
  });

  it("shows a failed search as an alert and still renders without categories", async () => {
    loadProductPage.mockResolvedValue(FAILURE);
    loadCategories.mockResolvedValue(FAILURE);

    inProviders(await ProductsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("alert")).toHaveTextContent("not available");
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument();
  });
});

describe("products page metadata", () => {
  it("is indexable for the plain listing", async () => {
    expect(await generateMetadata({ searchParams: Promise.resolve({}) })).toMatchObject({ title: "Products", robots: undefined });
  });

  it("names the search and keeps filtered or paged results out of the index", async () => {
    expect(await generateMetadata({ searchParams: Promise.resolve({ q: "shoes" }) })).toMatchObject({
      title: 'Results for "shoes"',
      robots: { index: false, follow: true },
    });
    expect(await generateMetadata({ searchParams: Promise.resolve({ cursor: "abc" }) })).toMatchObject({
      robots: { index: false },
    });
  });
});
