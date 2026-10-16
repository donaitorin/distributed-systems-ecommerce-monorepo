import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { CategoryCreated } from "../../server/category-actions";
import type { Failure } from "../../lib/failure";
import { UnknownCategoryAction } from "./unknown-category-action";
import { withAppProviders } from "../story-support";

const meta = {
  title: "Backoffice/Imports/UnknownCategoryAction",
  component: UnknownCategoryAction,
  parameters: { layout: "padded" },
  decorators: [withAppProviders()],
  args: {
    category: { value: "Gardening", rows: 2, suggestion: null },
    createCategory: (): Promise<CategoryCreated | Failure> =>
      Promise.resolve({ ok: true, category: { id: "c", name: "Gardening", slug: "gardening" } }),
    onAvailable: () => undefined,
  },
} satisfies Meta<typeof UnknownCategoryAction>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Created: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Create category Gardening" }));
    await expect(await canvas.findByText("Category created. Validate again to use it.")).toBeVisible();
  },
};

export const AlreadyExists: Story = {
  args: { createCategory: () => Promise.resolve({ ok: false as const, status: 409, title: "Exists", fieldErrors: {} }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Create category Gardening" }));
    await expect(await canvas.findByText(/already exists/)).toBeVisible();
  },
};

export const Failed: Story = {
  args: { createCategory: () => Promise.resolve({ ok: false as const, status: 422, title: "Invalid", fieldErrors: { name: "must contain letters or digits" } }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Create category Gardening" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("must contain letters or digits");
  },
};
