import { fireEvent, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { ProductImageEditor, type ProductImageEditorProps } from "../src/components/products/product-image-editor";
import { product } from "./support/api";
import { resetRouter, router } from "./support/navigation-mock";
import { renderApp } from "./support/render";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const WITH_IMAGE = product({
  image_url: "http://127.0.0.1:8000/media/media/products/RS-001/a-1200.webp",
  thumbnail_url: "http://127.0.0.1:8000/media/media/products/RS-001/a-400.webp",
});

const created: string[] = [];
const revoked: string[] = [];

beforeAll(() => {
  URL.createObjectURL = jest.fn(() => {
    const url = `blob:preview-${created.length}`;
    created.push(url);
    return url;
  });
  URL.revokeObjectURL = jest.fn((url: string) => {
    revoked.push(url);
  });
});

beforeEach(() => {
  resetRouter();
  created.length = 0;
  revoked.length = 0;
});

function setup(overrides: Partial<ProductImageEditorProps> = {}) {
  const uploadImage = jest.fn().mockResolvedValue({ ok: true, product: WITH_IMAGE, etag: '"4"' });
  const removeImage = jest.fn().mockResolvedValue({ ok: true, product: product(), etag: '"5"' });
  const onChanged = jest.fn();
  const view = renderApp(
    <ProductImageEditor
      product={product()}
      etag='"3"'
      uploadImage={uploadImage}
      removeImage={removeImage}
      onChanged={onChanged}
      {...overrides}
    />,
  );
  return { ...view, uploadImage, removeImage, onChanged };
}

function png(name = "shoe.png", size = 1000, type = "image/png"): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("ProductImageEditor", () => {
  it("shows the placeholder for a product without an image, has no remove button and no violations", async () => {
    const { container } = setup();

    expect(screen.getByRole("img", { name: "Running shoes has no image" })).toBeInTheDocument();
    expect(screen.getByLabelText("Upload an image")).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
    expect(screen.getByText("JPEG, PNG or WebP, up to 5 MB.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove image" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload image" })).toBeDisabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the current image from the page's own origin, with a way to replace and remove it", () => {
    setup({ product: WITH_IMAGE });

    expect(screen.getByAltText("Image of Running shoes")).toHaveAttribute("src", "/media/media/products/RS-001/a-400.webp");
    expect(screen.getByLabelText("Replace the image")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove image" })).toBeEnabled();
  });

  it("previews the chosen file, uploads it with the etag, and tells the parent the new etag", async () => {
    const { user, uploadImage, onChanged } = setup();
    const file = png();

    await user.upload(screen.getByLabelText("Upload an image"), file);
    expect(screen.getByAltText("Preview of the selected image")).toHaveAttribute("src", "blob:preview-0");
    await user.click(screen.getByRole("button", { name: "Upload image" }));

    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledWith(WITH_IMAGE, '"4"');
    });
    expect(uploadImage).toHaveBeenCalledWith("RS-001", '"3"', file);
    expect(await screen.findByText("The image of RS-001 was updated.")).toBeInTheDocument();
    expect(screen.getAllByRole("status").map((region) => region.textContent)).toContain("Image uploaded");
    expect(revoked).toContain("blob:preview-0");
  });

  it("rejects an unsupported or oversized file before sending anything, in plain language", async () => {
    const { user, uploadImage } = setup();

    const gif = png("a.gif", 100, "image/gif");
    fireEvent.change(screen.getByLabelText("Upload an image"), {
      target: { files: Object.assign([gif], { item: () => gif }) },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("not supported");
    expect(screen.getByLabelText("Upload an image")).toBeInvalid();
    expect(screen.getByRole("button", { name: "Upload image" })).toBeDisabled();

    await user.upload(screen.getByLabelText("Upload an image"), png("big.png", 5 * 1024 * 1024 + 1));
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 5 MB");
    expect(uploadImage).not.toHaveBeenCalled();
  });

  it.each([
    [413, "larger than 5 MB"],
    [415, "JPEG, PNG or WebP"],
    [422, "could not be used"],
    [503, "Image storage is not available"],
    [412, "changed by someone else"],
  ])("shows the backend's %s in plain language and keeps the selection", async (status, text) => {
    const { user, onChanged } = setup({
      uploadImage: jest.fn().mockResolvedValue({ ok: false, status, title: "Problem", fieldErrors: {}, retryAfterSeconds: 3 }),
    });

    await user.upload(screen.getByLabelText("Upload an image"), png());
    await user.click(screen.getByRole("button", { name: "Upload image" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Upload image" })).toBeEnabled();
  });

  it("clears the selection", async () => {
    const { user } = setup();

    await user.upload(screen.getByLabelText("Upload an image"), png());
    await user.click(screen.getByRole("button", { name: "Clear selection" }));

    expect(screen.getByRole("img", { name: "Running shoes has no image" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload image" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Clear selection" })).not.toBeInTheDocument();
  });

  it("sends an expired session to the login page", async () => {
    const { user } = setup({
      uploadImage: jest.fn().mockResolvedValue({ ok: false, status: 401, title: "Unauthorized", fieldErrors: {} }),
    });

    await user.upload(screen.getByLabelText("Upload an image"), png());
    await user.click(screen.getByRole("button", { name: "Upload image" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });

  it("asks for confirmation before removing, then removes with the etag", async () => {
    const { user, removeImage, onChanged } = setup({ product: WITH_IMAGE });

    await user.click(screen.getByRole("button", { name: "Remove image" }));
    expect(await screen.findByRole("dialog", { name: "Remove this image?" })).toBeInTheDocument();
    expect(removeImage).not.toHaveBeenCalled();
    await user.click(screen.getAllByRole("button", { name: "Remove image" }).at(-1) as HTMLElement);

    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledWith(product(), '"5"');
    });
    expect(removeImage).toHaveBeenCalledWith("RS-001", '"3"');
    expect(await screen.findByText("RS-001 has no image now.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("keeps the dialog open and explains a failed removal", async () => {
    const { user, onChanged } = setup({
      product: WITH_IMAGE,
      removeImage: jest.fn().mockResolvedValue({ ok: false, status: 404, title: "No image", fieldErrors: {} }),
    });

    await user.click(screen.getByRole("button", { name: "Remove image" }));
    await user.click((await screen.findAllByRole("button", { name: "Remove image" })).at(-1) as HTMLElement);

    const dialog = await screen.findByRole("dialog");
    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
    expect(dialog).toHaveTextContent("no image, or it no longer exists");
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("sends an expired session to the login page when removing", async () => {
    const { user } = setup({
      product: WITH_IMAGE,
      removeImage: jest.fn().mockResolvedValue({ ok: false, status: 403, title: "Forbidden", fieldErrors: {} }),
    });

    await user.click(screen.getByRole("button", { name: "Remove image" }));
    await user.click((await screen.findAllByRole("button", { name: "Remove image" })).at(-1) as HTMLElement);

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });
});
