import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import { FileDropzone } from "./file-dropzone";

const meta = {
  title: "Components/FileDropzone",
  component: FileDropzone,
  parameters: { layout: "padded" },
  args: {
    label: "Products CSV",
    accept: ".csv,text/csv",
    maxBytes: 50 * 1024 * 1024,
    hint: "A .csv file with a header row, up to 50 MB.",
    onFile: () => undefined,
  },
} satisfies Meta<typeof FileDropzone>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const FileTooLarge: Story = {
  args: { maxBytes: 10 },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.upload(canvas.getByLabelText("Choose a file"), new File(["a longer content"], "big.csv", { type: "text/csv" }));
    await expect(await canvas.findByRole("alert")).toHaveTextContent("larger than the 10 B limit");
  },
};

export const Uploading: Story = { args: { loading: true, loadingFileName: "products.csv" } };

export const UploadFailed: Story = { args: { error: "The server could not be reached. Try again in a moment." } };

export const Disabled: Story = { args: { disabled: true } };

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
