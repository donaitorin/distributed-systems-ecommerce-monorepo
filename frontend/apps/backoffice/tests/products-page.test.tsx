import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import ProductsPage from "../src/app/products/page";
import { CATEGORY, product } from "./support/api";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { NotificationsProvider } from "../src/components/notifications";

const loadProductPage = jest.fn();
const loadCategories = jest.fn();

jest.mock("../src/server/products", () => ({
  isFailure: (value: { ok?: boolean }) => value.ok === false,
  loadProductPage: (...args: unknown[]) => loadProductPage(...args) as unknown,
  loadCategories: () => loadCategories() as unknown,
}));

jest.mock("../src/app/products/actions", () => ({
  createProductAction: jest.fn(),
  updateProductAction: jest.fn(),
  deleteProductAction: jest.fn(),
  removeProductImageAction: jest.fn(),
}));

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

globalThis.Request ??= class Request {} as unknown as typeof Request;

const FAILURE = { ok: false, status: 500, title: "Boom", fieldErrors: {} };

function inProviders(element: React.ReactElement) {
  return render(
    <NuqsTestingAdapter>
      <NotificationsProvider>{element}</NotificationsProvider>
    </NuqsTestingAdapter>,
  );
}

beforeEach(() => {
  loadProductPage.mockReset();
  loadCategories.mockReset();
  loadCategories.mockResolvedValue([CATEGORY]);
});

describe("products page", () => {
  it("loads the page for the URL's search state and renders the heading, the link and the table", async () => {
    loadProductPage.mockResolvedValue({ items: [product()], next_cursor: null, prev_cursor: null, total: 1, total_exact: true });

    const { container } = inProviders(
      await ProductsPage({ searchParams: Promise.resolve({ q: "shoes", limit: "48", min_price: "abc" }) }),
    );

    expect(loadProductPage).toHaveBeenCalledWith(expect.objectContaining({ q: "shoes", limit: 48, min_price: null }));
    expect(screen.getByRole("heading", { level: 1, name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New product" })).toHaveAttribute("href", "/admin/products/new");
    expect(screen.getByRole("link", { name: "Import CSV" })).toHaveAttribute("href", "/admin/products/import");
    expect(screen.getAllByText("Running shoes").length).toBeGreaterThan(0);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a failed search as an alert instead of crashing, and still renders without categories", async () => {
    loadProductPage.mockResolvedValue(FAILURE);
    loadCategories.mockResolvedValue(FAILURE);

    inProviders(await ProductsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("Boom");
    expect(screen.getByRole("combobox", { name: "Category" })).toBeInTheDocument();
  });
});
