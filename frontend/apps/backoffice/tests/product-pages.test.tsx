import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import EditProductPage, { generateMetadata } from "../src/app/products/[sku]/page";
import NewProductPage from "../src/app/products/new/page";
import { CATEGORY, product } from "./support/api";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { NotificationsProvider } from "../src/components/notifications";

const loadCategories = jest.fn();
const loadProduct = jest.fn();

jest.mock("../src/server/products", () => ({
  isFailure: (value: { ok?: boolean }) => value.ok === false,
  loadCategories: () => loadCategories() as unknown,
  loadProduct: (...args: unknown[]) => loadProduct(...args) as unknown,
}));

jest.mock("../src/app/products/actions", () => ({
  createProductAction: jest.fn(),
  updateProductAction: jest.fn(),
  deleteProductAction: jest.fn(),
  removeProductImageAction: jest.fn(),
}));

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const FAILURE = { ok: false, status: 500, title: "Boom", fieldErrors: {} };

function inProviders(element: React.ReactElement) {
  return render(
    <NuqsTestingAdapter>
      <NotificationsProvider>{element}</NotificationsProvider>
    </NuqsTestingAdapter>,
  );
}

beforeEach(() => {
  loadCategories.mockReset();
  loadProduct.mockReset();
  loadCategories.mockResolvedValue([CATEGORY]);
});

describe("new product page", () => {
  it("renders the create form with the categories", async () => {
    const { container } = inProviders(await NewProductPage());

    expect(screen.getByRole("heading", { level: 1, name: "New product" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "New product" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("warns when the categories could not be loaded", async () => {
    loadCategories.mockResolvedValue(FAILURE);

    inProviders(await NewProductPage());

    expect(screen.getByRole("alert")).toHaveTextContent("categories could not be loaded");
  });
});

describe("edit product page", () => {
  const params = (sku: string) => ({ params: Promise.resolve({ sku }) });

  it("loads the product by SKU and renders the editor with its etag", async () => {
    loadProduct.mockResolvedValue({ value: product(), etag: '"3"' });

    const { container } = inProviders(await EditProductPage(params("RS-001")));

    expect(loadProduct).toHaveBeenCalledWith("RS-001");
    expect(screen.getByRole("heading", { level: 1, name: "Edit product" })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Running shoes");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("decodes the SKU from the URL", async () => {
    loadProduct.mockResolvedValue({ value: product({ sku: "A/B" }), etag: '"3"' });

    inProviders(await EditProductPage(params("A%2FB")));

    expect(loadProduct).toHaveBeenCalledWith("A/B");
  });

  it("shows the not found page for an unknown SKU", async () => {
    loadProduct.mockResolvedValue({ ok: false, status: 404, title: "Not found", fieldErrors: {} });

    await expect(EditProductPage(params("NOPE"))).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("shows an alert for other load failures", async () => {
    loadProduct.mockResolvedValue(FAILURE);

    inProviders(await EditProductPage(params("RS-001")));

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  });

  it("titles the page with the SKU", async () => {
    expect(await generateMetadata(params("RS%2D001"))).toEqual({ title: "Edit RS-001" });
  });
});
