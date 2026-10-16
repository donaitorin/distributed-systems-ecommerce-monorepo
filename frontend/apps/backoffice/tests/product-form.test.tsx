import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { ProductForm, type ProductFormProps } from "../src/components/products/product-form";
import type { ProductFormValues } from "../src/lib/product-form";
import type { UpdateResult } from "../src/server/product-actions";
import { CATEGORY, product } from "./support/api";
import { resetRouter, router } from "./support/navigation-mock";
import { renderApp } from "./support/render";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const CATEGORIES = [CATEGORY, { id: "5a1b2c3d-0000-4000-8000-000000000002", name: "Toys", slug: "toys" }];

type Submit = jest.Mock<Promise<UpdateResult>, [ProductFormValues]>;

function submitting(result: unknown): Submit {
  return jest.fn<Promise<UpdateResult>, [ProductFormValues]>().mockResolvedValue(result as UpdateResult);
}

function setup(overrides: Partial<ProductFormProps> & { submit?: Submit } = {}) {
  const submit: Submit = overrides.submit ?? submitting({ ok: true, product: product({ sku: "NEW-1" }), etag: '"1"' });
  const onSaved = jest.fn();
  const view = renderApp(
    <ProductForm mode="create" categories={CATEGORIES} {...overrides} submit={submit} onSaved={onSaved} />,
  );
  return { ...view, submit, onSaved };
}

async function fillValid(user: ReturnType<typeof setup>["user"]) {
  await user.type(screen.getByLabelText("SKU"), "new-1");
  await user.type(screen.getByLabelText("Name"), "New shoes");
  await user.type(screen.getByLabelText("Price"), "19.9");
  await user.type(screen.getByLabelText("Stock"), "5");
}

function failure(status: number | null, extra: object = {}) {
  return { ok: false, status, title: "Problem", fieldErrors: {}, ...extra };
}

beforeEach(() => {
  resetRouter();
});

describe("ProductForm validation", () => {
  it("labels every field and has no accessibility violations", async () => {
    const { container } = setup();

    for (const label of ["SKU", "Name", "Description", "Category", "Price", "Stock", "Weight (kg)"]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(await axe(container)).toHaveNoViolations();
  });

  it("blocks an empty submit, marks each invalid field and moves focus to the first one", async () => {
    const { user, submit, container } = setup();

    await user.click(screen.getByRole("button", { name: "Create product" }));

    await waitFor(() => {
      expect(screen.getByLabelText("SKU")).toHaveFocus();
    });
    expect(submit).not.toHaveBeenCalled();
    for (const label of ["SKU", "Name", "Price", "Stock"]) {
      expect(screen.getByLabelText(label)).toHaveAttribute("aria-invalid", "true");
    }
    expect(screen.getByLabelText("SKU")).toHaveAccessibleDescription(expect.stringContaining("SKU is required"));
    expect(screen.getByLabelText("Weight (kg)")).not.toHaveAttribute("aria-invalid");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("focuses the first invalid field in form order, not the first one touched", async () => {
    const { user } = setup();
    await user.type(screen.getByLabelText("SKU"), "ok-1");
    await user.type(screen.getByLabelText("Name"), "Name");

    await user.click(screen.getByRole("button", { name: "Create product" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Price")).toHaveFocus();
    });
  });

  it("clears an error as soon as the field is fixed", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Create product" }));
    await screen.findByText("Name is required");

    await user.type(screen.getByLabelText("Name"), "Shoes");

    await waitFor(() => {
      expect(screen.queryByText("Name is required")).not.toBeInTheDocument();
    });
  });
});

describe("ProductForm create", () => {
  it("submits the values as typed, with money still a string, then goes to the edit page", async () => {
    const { user, submit } = setup();
    await fillValid(user);

    await user.click(screen.getByLabelText("Category"));
    await user.click(await screen.findByRole("option", { name: "Toys" }));
    await user.click(screen.getByRole("button", { name: "Create product" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/products/NEW-1");
    });
    expect(submit).toHaveBeenCalledWith({
      sku: "new-1",
      name: "New shoes",
      description: "",
      categoryId: "5a1b2c3d-0000-4000-8000-000000000002",
      price: "19.9",
      stock: "5",
      weightKg: "",
    });
    expect(await screen.findByText(/NEW-1 is in the catalog/)).toBeInTheDocument();
  });

  it("can go back to no category", async () => {
    const { user, submit } = setup();
    await fillValid(user);
    await user.click(screen.getByLabelText("Category"));
    await user.click(await screen.findByRole("option", { name: "Sports" }));
    await user.click(screen.getByLabelText("Category"));
    await user.click(await screen.findByRole("option", { name: "No category" }));
    await user.click(screen.getByRole("button", { name: "Create product" }));

    await waitFor(() => {
      expect(submit).toHaveBeenCalledWith(expect.objectContaining({ categoryId: "" }));
    });
  });

  it("explains a SKU that is already in use, on the field, and focuses it", async () => {
    const { user } = setup({ submit: submitting(failure(409)) });
    await fillValid(user);

    await user.click(screen.getByRole("button", { name: "Create product" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("SKUs of deleted products stay reserved");
    expect(screen.getByLabelText("SKU")).toHaveAccessibleDescription(
      expect.stringContaining("already in use, possibly by a deleted product"),
    );
    await waitFor(() => {
      expect(screen.getByLabelText("SKU")).toHaveFocus();
    });
    expect(router.push).not.toHaveBeenCalled();
  });

  it("shows the API's field errors on the fields, including the category", async () => {
    const { user } = setup({
      submit: jest.fn().mockResolvedValue(
        failure(422, { fieldErrors: { price: "must not be negative", category_id: "unknown category", weight_kg: "too heavy" } }),
      ),
    });
    await fillValid(user);

    await user.click(screen.getByRole("button", { name: "Create product" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Category")).toHaveFocus();
    });
    expect(screen.getByLabelText("Price")).toHaveAccessibleDescription(expect.stringContaining("must not be negative"));
    expect(screen.getByLabelText("Category")).toHaveAccessibleDescription("unknown category");
    expect(screen.getByLabelText("Weight (kg)")).toHaveAccessibleDescription(expect.stringContaining("too heavy"));
  });

  it("puts a failure without field errors in a focused alert", async () => {
    const { user } = setup({ submit: submitting(failure(503, { retryAfterSeconds: 2 })) });
    await fillValid(user);

    await user.click(screen.getByRole("button", { name: "Create product" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Try again in 2 seconds");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
    expect(await screen.findByText("The product was not saved")).toBeInTheDocument();
  });

  it("sends an expired session to the login page", async () => {
    const { user } = setup({ submit: submitting(failure(401)) });
    await fillValid(user);

    await user.click(screen.getByRole("button", { name: "Create product" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });
});

describe("ProductForm edit", () => {
  const existing = product();

  function edit(submit: Submit) {
    return setup({ mode: "edit", product: existing, submit });
  }

  it("shows the product, keeps the SKU read only and has no accessibility violations", async () => {
    const { container } = edit(submitting({ ok: true, product: product(), etag: '"3"' }));

    expect(screen.getByLabelText("SKU")).toHaveValue("RS-001");
    expect(screen.getByLabelText("SKU")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Name")).toHaveValue("Running shoes");
    expect(screen.getByLabelText("Category")).toHaveTextContent("Sports");
    expect(screen.getByLabelText("Price")).toHaveValue("59.00");
    expect(screen.getByLabelText("Weight (kg)")).toHaveValue("0.800");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows no category for a product without one", () => {
    setup({ mode: "edit", product: product({ category: null }), submit: submitting({ ok: true, product: product(), etag: '"3"' }) });

    expect(screen.getByLabelText("Category")).toHaveTextContent("No category");
  });

  it("saves and reports the new version to the parent", async () => {
    const saved = product({ name: "Trail shoes", version: 4 });
    const { user, submit, onSaved } = edit(submitting({ ok: true, product: saved, etag: '"4"' }));

    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Trail shoes");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(saved, '"4"');
    });
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ name: "Trail shoes", price: "59.00" }));
    expect(await screen.findByText("RS-001 was updated.")).toBeInTheDocument();
    expect(router.push).not.toHaveBeenCalled();
  });

  describe("on a conflict (412)", () => {
    const latest = { value: product({ name: "Boots", price: "75.00", version: 5 }), etag: '"5"' };

    async function conflict(result: object) {
      const view = edit(submitting(result));
      await view.user.clear(screen.getByLabelText("Name"));
      await view.user.type(screen.getByLabelText("Name"), "My shoes");
      await view.user.click(screen.getByRole("button", { name: "Save changes" }));
      await screen.findByRole("dialog", { name: "This product was changed by someone else" });
      return view;
    }

    it("lists the fields that differ and does not discard the input silently", async () => {
      await conflict(failure(412, { latest }));
      const dialog = screen.getByRole("dialog");

      expect(within(dialog).getByText("Fields that differ:")).toBeInTheDocument();
      const items = within(dialog).getAllByRole("listitem");
      expect(items).toHaveLength(2);
      expect(items[0]).toHaveTextContent("Name");
      expect(items[0]).toHaveTextContent(/Your value:\s*My shoes/);
      expect(items[0]).toHaveTextContent(/Current value:\s*Boots/);
      expect(items[1]).toHaveTextContent("Price");
      expect(items[1]).toHaveTextContent(/Current value:\s*75.00/);
      expect(screen.getByLabelText("Name")).toHaveValue("My shoes");
      expect(await axe(document.body)).toHaveNoViolations();
    });

    it("keeps the user's input and adopts the latest version number when asked to", async () => {
      const { user, onSaved } = await conflict(failure(412, { latest }));

      await user.click(screen.getByRole("button", { name: "Keep my changes and overwrite" }));

      expect(onSaved).toHaveBeenCalledWith(latest.value, '"5"');
      expect(screen.getByLabelText("Name")).toHaveValue("My shoes");
      await waitFor(() => {
        expect(screen.queryByRole("dialog", { name: "This product was changed by someone else" })).not.toBeInTheDocument();
      });
      expect(await screen.findByText("Your changes were kept")).toBeInTheDocument();
    });

    it("loads the latest values only when the user chooses to discard", async () => {
      const { user, onSaved } = await conflict(failure(412, { latest }));

      await user.click(screen.getByRole("button", { name: "Discard my changes and load the latest" }));

      expect(onSaved).toHaveBeenCalledWith(latest.value, '"5"');
      expect(screen.getByLabelText("Name")).toHaveValue("Boots");
      expect(screen.getByLabelText("Price")).toHaveValue("75.00");
      expect(await screen.findByText("Latest version loaded")).toBeInTheDocument();
    });

    it("leaves everything untouched when the dialog is dismissed", async () => {
      const { user, onSaved } = await conflict(failure(412, { latest }));

      await user.keyboard("{Escape}");

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
      expect(onSaved).not.toHaveBeenCalled();
      expect(screen.getByLabelText("Name")).toHaveValue("My shoes");
    });

    it("says so when the other change touched none of the edited fields", async () => {
      const unchanged = { value: product({ name: "My shoes", version: 5 }), etag: '"5"' };
      await conflict(failure(412, { latest: unchanged }));

      expect(within(screen.getByRole("dialog")).getByText(/did not touch the fields you edited/)).toBeInTheDocument();
    });

    it("explains when the latest version could not be loaded and offers only to close", async () => {
      const { user, onSaved } = await conflict(failure(412));
      const dialog = screen.getByRole("dialog");

      expect(dialog).toHaveAccessibleDescription(expect.stringContaining("could not be loaded"));
      expect(within(dialog).queryByRole("button", { name: /overwrite/ })).not.toBeInTheDocument();
      await user.click(within(dialog).getAllByRole("button", { name: "Close" })[0] as HTMLElement);

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
      expect(onSaved).not.toHaveBeenCalled();
    });

    it("shows category names, not ids, in the differences", async () => {
      const toys = { value: product({ category: CATEGORIES[1] ?? null, version: 5 }), etag: '"5"' };
      await conflict(failure(412, { latest: toys }));

      const item = within(screen.getByRole("dialog")).getAllByRole("listitem").find((entry) => entry.textContent?.startsWith("Category"));
      expect(item).toHaveTextContent(/Your value:\s*Sports/);
      expect(item).toHaveTextContent(/Current value:\s*Toys/);
    });
  });

  it("explains a product that was deleted meanwhile", async () => {
    const { user } = edit(submitting(failure(404)));

    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("no longer exists");
  });
});
