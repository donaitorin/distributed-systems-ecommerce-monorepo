import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { UpdateResult } from "../../server/product-actions";
import { ProductForm } from "./product-form";
import { STORY_CATEGORIES, STORY_PRODUCT, withAppProviders } from "../story-support";

const saved = (): Promise<UpdateResult> => Promise.resolve({ ok: true, product: STORY_PRODUCT, etag: '"4"' });

const meta = {
  title: "Backoffice/ProductForm",
  component: ProductForm,
  parameters: { layout: "padded" },
  decorators: [withAppProviders()],
  args: { mode: "create", categories: STORY_CATEGORIES, submit: saved },
} satisfies Meta<typeof ProductForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Create: Story = {};

export const EmptySubmit: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Create product" }));
    await expect(await canvas.findByText("SKU is required")).toBeVisible();
    await expect(canvas.getByLabelText("SKU")).toHaveFocus();
  },
};

export const DuplicateSku: Story = {
  args: {
    submit: () => Promise.resolve({ ok: false, status: 409, title: "SKU already exists", fieldErrors: {} }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("SKU"), "rs-001");
    await userEvent.type(canvas.getByLabelText("Name"), "Running shoes");
    await userEvent.type(canvas.getByLabelText("Price"), "59");
    await userEvent.type(canvas.getByLabelText("Stock"), "1");
    await userEvent.click(canvas.getByRole("button", { name: "Create product" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("stay reserved");
  },
};

export const Edit: Story = { args: { mode: "edit", product: STORY_PRODUCT } };

export const ServerFieldErrors: Story = {
  args: {
    mode: "edit",
    product: STORY_PRODUCT,
    submit: () =>
      Promise.resolve({
        ok: false,
        status: 422,
        title: "Validation failed",
        fieldErrors: { price: "must not be negative", category_id: "unknown category" },
      }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Save changes" }));
    await expect(await canvas.findByText("unknown category")).toBeVisible();
  },
};

export const Conflict: Story = {
  args: {
    mode: "edit",
    product: STORY_PRODUCT,
    submit: () =>
      Promise.resolve({
        ok: false,
        status: 412,
        title: "Precondition failed",
        fieldErrors: {},
        latest: { value: { ...STORY_PRODUCT, name: "Boots", price: "75.00", version: 5 }, etag: '"5"' },
      }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.clear(canvas.getByLabelText("Name"));
    await userEvent.type(canvas.getByLabelText("Name"), "My shoes");
    await userEvent.click(canvas.getByRole("button", { name: "Save changes" }));
    await expect(
      await within(canvasElement.ownerDocument.body).findByRole("dialog", { name: "This product was changed by someone else" }),
    ).toBeVisible();
  },
};

export const Mobile: Story = {
  args: { mode: "edit", product: STORY_PRODUCT },
  globals: { viewport: { value: "mobile", isRotated: false } },
};
