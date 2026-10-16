import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { ImportQueryProvider } from "../src/components/imports/import-query-provider";
import { NotificationsProvider } from "../src/components/notifications";
import ImportProductsPage from "../src/app/products/import/page";

jest.mock("../src/app/products/import/actions", () => ({ confirmImportAction: jest.fn(), revalidateImportAction: jest.fn() }));
jest.mock("../src/app/categories/actions", () => ({ createCategoryAction: jest.fn() }));
jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

function renderPage() {
  return render(
    <NuqsTestingAdapter>
      <NotificationsProvider>{ImportProductsPage()}</NotificationsProvider>
    </NuqsTestingAdapter>,
  );
}

describe("import page", () => {
  const saved = process.env.IMPORT_MAX_BYTES;

  afterEach(() => {
    if (saved === undefined) {
      delete process.env.IMPORT_MAX_BYTES;
    } else {
      process.env.IMPORT_MAX_BYTES = saved;
    }
  });

  it("has one level 1 heading, a way back to the products and the upload step, without violations", async () => {
    const { container } = renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Import products from CSV" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to products" })).toHaveAttribute("href", "/admin/products");
    expect(screen.getByRole("group", { name: "Products CSV file" })).toBeInTheDocument();
    expect(screen.getByText(/Up to 50 MB/)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the limit the backend uses", () => {
    process.env.IMPORT_MAX_BYTES = String(5 * 1024 * 1024);

    renderPage();

    expect(screen.getByText(/Up to 5 MB/)).toBeInTheDocument();
  });
});

describe("ImportQueryProvider", () => {
  it("renders its children", () => {
    render(
      <ImportQueryProvider>
        <p>inside</p>
      </ImportQueryProvider>,
    );

    expect(screen.getByText("inside")).toBeInTheDocument();
  });
});
