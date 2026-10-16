/**
 * @jest-environment node
 */
import {
  createProductAction,
  deleteProductAction,
  removeProductImageAction,
  updateProductAction,
} from "../src/app/products/actions";
import type { ProductFormValues } from "../src/lib/product-form";

const createProduct = jest.fn();
const updateProduct = jest.fn();
const deleteProduct = jest.fn();
const removeProductImage = jest.fn();

jest.mock("../src/server/product-actions", () => ({
  createProduct: (...args: unknown[]) => createProduct(...args) as unknown,
  updateProduct: (...args: unknown[]) => updateProduct(...args) as unknown,
  deleteProduct: (...args: unknown[]) => deleteProduct(...args) as unknown,
  removeProductImage: (...args: unknown[]) => removeProductImage(...args) as unknown,
}));

const VALUES: ProductFormValues = { sku: "A", name: "B", description: "", categoryId: "", price: "1", stock: "1", weightKg: "" };

describe("product server actions", () => {
  it("delegate to the server logic and return its result", async () => {
    createProduct.mockResolvedValue("created");
    updateProduct.mockResolvedValue("updated");
    deleteProduct.mockResolvedValue("deleted");
    removeProductImage.mockResolvedValue("removed");

    expect(await createProductAction(VALUES)).toBe("created");
    expect(await updateProductAction("A", '"1"', VALUES)).toBe("updated");
    expect(await deleteProductAction("A", '"1"')).toBe("deleted");
    expect(await removeProductImageAction("A", '"1"')).toBe("removed");
    expect(updateProduct).toHaveBeenCalledWith("A", '"1"', VALUES);
  });
});
