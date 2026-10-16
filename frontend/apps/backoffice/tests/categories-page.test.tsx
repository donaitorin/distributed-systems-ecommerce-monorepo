import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import CategoriesPage from "../src/app/categories/page";
import { NotificationsProvider } from "../src/components/notifications";
import { CATEGORY } from "./support/api";

const loadCategories = jest.fn();

jest.mock("../src/server/products", () => ({
  isFailure: (value: { ok?: boolean }) => value.ok === false,
  loadCategories: () => loadCategories() as unknown,
}));
jest.mock("../src/app/categories/actions", () => ({ createCategoryAction: jest.fn() }));

function inProviders(element: React.ReactElement) {
  return render(
    <NuqsTestingAdapter>
      <NotificationsProvider>{element}</NotificationsProvider>
    </NuqsTestingAdapter>,
  );
}

beforeEach(() => {
  loadCategories.mockReset();
});

describe("categories page", () => {
  it("lists the categories under a level 1 heading", async () => {
    loadCategories.mockResolvedValue([CATEGORY]);

    const { container } = inProviders(await CategoriesPage());

    expect(screen.getByRole("heading", { level: 1, name: "Categories" })).toBeInTheDocument();
    expect(screen.getAllByText("Sports").length).toBeGreaterThan(0);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the failure instead of crashing", async () => {
    loadCategories.mockResolvedValue({ ok: false, status: 500, title: "Boom", fieldErrors: {} });

    inProviders(await CategoriesPage());

    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("could not be loaded");
  });
});
