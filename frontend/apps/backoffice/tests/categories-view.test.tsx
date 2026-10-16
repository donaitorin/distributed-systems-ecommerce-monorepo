import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { CategoriesView, type CategoriesViewProps } from "../src/components/categories/categories-view";
import type { CategoryFormValues } from "../src/lib/category-form";
import type { Failure } from "../src/lib/failure";
import type { CategoryCreated } from "../src/server/category-actions";
import { CATEGORY } from "./support/api";
import { resetRouter, router } from "./support/navigation-mock";
import { renderApp } from "./support/render";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const TOYS = { id: "5a1b2c3d-0000-4000-8000-000000000002", name: "Toys", slug: "toys" };
const BOOKS = { id: "5a1b2c3d-0000-4000-8000-000000000003", name: "books", slug: "books" };

type Create = jest.Mock<Promise<CategoryCreated | Failure>, [CategoryFormValues]>;

function creating(result: CategoryCreated | Failure): Create {
  return jest.fn<Promise<CategoryCreated | Failure>, [CategoryFormValues]>().mockResolvedValue(result);
}

function setup(overrides: Partial<CategoriesViewProps> & { createCategory?: Create } = {}) {
  const createCategory = overrides.createCategory ?? creating({ ok: true, category: TOYS });
  const view = renderApp(
    <CategoriesView categories={[TOYS, CATEGORY, BOOKS]} failure={null} {...overrides} createCategory={createCategory} />,
  );
  return { ...view, createCategory };
}

function failure(status: number | null, extra: object = {}): Failure {
  return { ok: false, status, title: "Problem", fieldErrors: {}, ...extra };
}

beforeEach(() => {
  resetRouter();
});

describe("CategoriesView", () => {
  it("lists the categories alphabetically, as a table and as cards, without accessibility violations", async () => {
    const { container } = setup();

    const table = screen.getByRole("table", { name: "Category list" });
    expect(within(table).getAllByRole("row").slice(1).map((row) => row.textContent)).toEqual([
      "bookssbooks".replace("sbooks", "books"),
      "Sportssports",
      "Toystoys",
    ]);
    expect(within(screen.getByRole("list", { name: "Category list" })).getAllByRole("listitem")).toHaveLength(3);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows an alert instead of the list when the categories could not be loaded, and the empty message", () => {
    const { unmount } = setup({ categories: [], failure: failure(500) });
    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent("could not be loaded");
    unmount();

    setup({ categories: [] });
    expect(within(screen.getByRole("table")).getByText("There are no categories yet.")).toBeInTheDocument();
  });

  it("creates a category, announces it, clears and refocuses the field and refreshes the list", async () => {
    const { user, createCategory } = setup();

    await user.type(screen.getByLabelText("New category name"), "  Toys  ");
    await user.click(screen.getByRole("button", { name: "Create category" }));

    await waitFor(() => {
      expect(router.refresh).toHaveBeenCalledTimes(1);
    });
    expect(createCategory).toHaveBeenCalledWith({ name: "  Toys  " });
    expect(await screen.findByText("Toys is available for products.")).toBeInTheDocument();
    expect(screen.getByLabelText("New category name")).toHaveValue("");
    await waitFor(() => {
      expect(screen.getByLabelText("New category name")).toHaveFocus();
    });
  });

  it("blocks an empty submit, marks the field invalid and focuses it", async () => {
    const { user, createCategory, container } = setup();

    await user.click(screen.getByRole("button", { name: "Create category" }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(screen.getByLabelText("New category name")).toBeInvalid();
    expect(screen.getByLabelText("New category name")).toHaveAccessibleDescription(expect.stringContaining("Name is required"));
    await waitFor(() => {
      expect(screen.getByLabelText("New category name")).toHaveFocus();
    });
    expect(createCategory).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a duplicate name on the field and focuses it", async () => {
    const { user } = setup({ createCategory: creating(failure(409)) });

    await user.type(screen.getByLabelText("New category name"), "Sports");
    await user.click(screen.getByRole("button", { name: "Create category" }));

    const field = screen.getByLabelText("New category name");
    await waitFor(() => {
      expect(field).toHaveAccessibleDescription(expect.stringContaining("already exists"));
    });
    expect(field).toBeInvalid();
    await waitFor(() => {
      expect(field).toHaveFocus();
    });
    expect(screen.queryByRole("alert")).toHaveTextContent("already exists");
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("shows the API's validation message on the field", async () => {
    const { user } = setup({ createCategory: creating(failure(422, { fieldErrors: { name: "must contain letters or digits" } })) });

    await user.type(screen.getByLabelText("New category name"), "Sports");
    await user.click(screen.getByRole("button", { name: "Create category" }));

    await waitFor(() => {
      expect(screen.getByLabelText("New category name")).toHaveAccessibleDescription(
        expect.stringContaining("must contain letters or digits"),
      );
    });
  });

  it("puts other failures in a focused alert", async () => {
    const { user } = setup({ createCategory: creating(failure(503, { retryAfterSeconds: 4 })) });

    await user.type(screen.getByLabelText("New category name"), "Sports");
    await user.click(screen.getByRole("button", { name: "Create category" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Try again in 4 seconds");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
  });

  it("sends an expired session to the login page", async () => {
    const { user } = setup({ createCategory: creating(failure(401)) });

    await user.type(screen.getByLabelText("New category name"), "Sports");
    await user.click(screen.getByRole("button", { name: "Create category" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });
});
