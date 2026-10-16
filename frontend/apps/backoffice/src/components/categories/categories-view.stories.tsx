import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { CategoryCreated } from "../../server/category-actions";
import type { Failure } from "../../lib/failure";
import { STORY_CATEGORIES, withAppProviders } from "../story-support";
import { CategoriesView } from "./categories-view";

const created = (): Promise<CategoryCreated | Failure> => Promise.resolve({ ok: true, category: { id: "x", name: "Garden", slug: "garden" } });
const rejected = (status: number): (() => Promise<CategoryCreated | Failure>) => () =>
  Promise.resolve({ ok: false, status, title: "Problem", fieldErrors: {} });

const meta = {
  title: "Backoffice/CategoriesView",
  component: CategoriesView,
  parameters: { layout: "padded" },
  decorators: [withAppProviders()],
  args: { categories: STORY_CATEGORIES, failure: null, createCategory: created },
} satisfies Meta<typeof CategoriesView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = { args: { categories: [] } };

export const LoadFailed: Story = {
  args: { categories: [], failure: { ok: false, status: 500, title: "Boom", fieldErrors: {} } },
};

export const EmptyName: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "Create category" }));
    await expect(await canvas.findByText("Name is required")).toBeVisible();
    await expect(canvas.getByLabelText("New category name")).toHaveFocus();
  },
};

export const DuplicateName: Story = {
  args: { createCategory: rejected(409) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("New category name"), "Sports");
    await userEvent.click(canvas.getByRole("button", { name: "Create category" }));
    await expect(await canvas.findAllByText(/already exists/)).not.toHaveLength(0);
    await expect(canvas.getByLabelText("New category name")).toBeInvalid();
  },
};

export const Unavailable: Story = {
  args: { createCategory: rejected(503) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText("New category name"), "Garden");
    await userEvent.click(canvas.getByRole("button", { name: "Create category" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("not available");
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
