import { screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { ProductEditor } from "../src/components/products/product-editor";
import { CATEGORY, product } from "./support/api";
import { resetRouter, router } from "./support/navigation-mock";
import { renderApp } from "./support/render";
import { settled } from "@ecommerce/web-core/testing";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

beforeEach(() => {
  resetRouter();
});

function setup(overrides: Partial<Parameters<typeof ProductEditor>[0]> = {}) {
  const updateProduct = jest.fn().mockResolvedValue({ ok: true, product: product({ name: "Trail", version: 4 }), etag: '"4"' });
  const deleteProduct = jest.fn().mockResolvedValue({ ok: true });
  const removeImage = jest.fn();
  const uploadImage = jest.fn().mockResolvedValue({
    ok: true,
    product: product({ version: 5, image_url: "/media/a-1200.webp", thumbnail_url: "/media/a-400.webp" }),
    etag: '"5"',
  });
  const view = renderApp(
    <ProductEditor
      categories={[CATEGORY]}
      initial={{ product: product(), etag: '"3"' }}
      updateProduct={updateProduct}
      deleteProduct={deleteProduct}
      removeImage={removeImage}
      uploadImage={uploadImage}
      {...overrides}
    />,
  );
  return { ...view, updateProduct, deleteProduct, removeImage, uploadImage };
}

describe("ProductEditor", () => {
  it("composes the form, the image section and the delete section without violations", async () => {
    const { container } = setup();

    expect(screen.getByRole("form", { name: "Edit product" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Image" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Delete product" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("saves with the etag it loaded and then uses the etag the save returned", async () => {
    const { user, updateProduct } = setup();

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      expect(updateProduct).toHaveBeenCalledWith("RS-001", '"3"', expect.objectContaining({ name: "Running shoes" }));
    });
    await screen.findByText("RS-001 was updated.");
    await settled();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateProduct).toHaveBeenLastCalledWith("RS-001", '"4"', expect.anything());
    });
  });

  it("uses the etag the image upload returned for the next save", async () => {
    const { user, updateProduct } = setup();
    const file = new File(["x"], "a.png", { type: "image/png" });

    await user.upload(screen.getByLabelText("Upload an image"), file);
    await user.click(screen.getByRole("button", { name: "Upload image" }));
    await screen.findByText("The image of RS-001 was updated.");
    await settled();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateProduct).toHaveBeenCalledWith("RS-001", '"5"', expect.anything());
    });
  });

  it("deletes with the current etag and returns to the list", async () => {
    const { user, deleteProduct } = setup();

    await user.click(screen.getAllByRole("button", { name: "Delete product" })[0] as HTMLElement);
    await user.click((await screen.findAllByRole("button", { name: "Delete product" })).at(-1) as HTMLElement);

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/products");
    });
    expect(deleteProduct).toHaveBeenCalledWith("RS-001", '"3"');
  });

  it("closes the delete dialog on cancel", async () => {
    const { user, deleteProduct } = setup();

    await user.click(screen.getAllByRole("button", { name: "Delete product" })[0] as HTMLElement);
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(deleteProduct).not.toHaveBeenCalled();
  });

  it("uploads through the browser upload function when none is injected", async () => {
    const original = global.fetch;
    const send = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => '"6"' },
      json: () => Promise.resolve(product({ version: 6 })),
    });
    global.fetch = send;
    try {
      const { user } = setup({ uploadImage: undefined });

      await user.upload(screen.getByLabelText("Upload an image"), new File(["x"], "a.png", { type: "image/png" }));
      await user.click(screen.getByRole("button", { name: "Upload image" }));

      await waitFor(() => {
        expect(send).toHaveBeenCalledWith("/admin/api/stream/products/RS-001/image", expect.objectContaining({ method: "PUT" }));
      });
    } finally {
      global.fetch = original;
    }
  });
});
