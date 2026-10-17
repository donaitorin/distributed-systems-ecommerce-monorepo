import { screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { DeleteProductDialog } from "../src/components/delete-product-dialog";
import { router, resetRouter } from "./support/navigation-mock";
import { renderApp } from "./support/render";
import { settled } from "@ecommerce/web-core/testing";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const TARGET = { sku: "RS-001", name: "Running shoes", version: 3 };

function setup(deleteProduct = jest.fn().mockResolvedValue({ ok: true })) {
  const onClose = jest.fn();
  const onDeleted = jest.fn();
  const view = renderApp(
    <DeleteProductDialog product={TARGET} deleteProduct={deleteProduct} onClose={onClose} onDeleted={onDeleted} />,
  );
  return { ...view, deleteProduct, onClose, onDeleted };
}

beforeEach(() => {
  resetRouter();
});

describe("DeleteProductDialog", () => {
  it("names the product and has no accessibility violations", async () => {
    setup();

    expect(await screen.findByRole("dialog", { name: "Delete this product?" })).toHaveAccessibleDescription(
      /RS-001, Running shoes/,
    );
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("is closed without a product", () => {
    renderApp(<DeleteProductDialog product={null} deleteProduct={jest.fn()} onClose={jest.fn()} onDeleted={jest.fn()} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("deletes with the etag derived from the version the administrator saw", async () => {
    const { user, deleteProduct, onDeleted } = setup();

    await user.click(await screen.findByRole("button", { name: "Delete product" }));

    await waitFor(() => {
      expect(onDeleted).toHaveBeenCalledTimes(1);
    });
    expect(deleteProduct).toHaveBeenCalledWith("RS-001", '"3"');
    expect(await screen.findByText("RS-001 was removed from the catalog.")).toBeInTheDocument();
  });

  it("uses the etag it is given", async () => {
    const deleteProduct = jest.fn().mockResolvedValue({ ok: true });
    const { user } = renderApp(
      <DeleteProductDialog product={TARGET} etag='"9"' deleteProduct={deleteProduct} onClose={jest.fn()} onDeleted={jest.fn()} />,
    );

    await user.click(await screen.findByRole("button", { name: "Delete product" }));

    await waitFor(() => {
      expect(deleteProduct).toHaveBeenCalledWith("RS-001", '"9"');
    });
  });

  it("keeps the dialog open and explains a stale version", async () => {
    const { user, onDeleted } = setup(jest.fn().mockResolvedValue({ ok: false, status: 412, title: "Precondition failed", fieldErrors: {} }));

    await user.click(await screen.findByRole("button", { name: "Delete product" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("changed by someone else");
    expect(onDeleted).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("clears the error when it is cancelled", async () => {
    const { user, onClose } = setup(jest.fn().mockResolvedValue({ ok: false, status: 404, title: "Not found", fieldErrors: {} }));

    await user.click(await screen.findByRole("button", { name: "Delete product" }));
    await screen.findByRole("alert");
    await settled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("sends an expired session to the login page", async () => {
    const { user } = setup(jest.fn().mockResolvedValue({ ok: false, status: 401, title: "Unauthorized", fieldErrors: {} }));

    await user.click(await screen.findByRole("button", { name: "Delete product" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });
});
