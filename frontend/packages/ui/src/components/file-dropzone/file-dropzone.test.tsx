import { createEvent, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { FileDropzone, type FileDropzoneProps } from "./file-dropzone";
import { formatBytes } from "./format-bytes";

function csv(name = "products.csv", size = 100, type = "text/csv"): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

function setup(props: Partial<FileDropzoneProps> = {}) {
  const onFile = jest.fn();
  const view = render(<FileDropzone label="Products CSV" onFile={onFile} accept=".csv,text/csv" {...props} />);
  return { ...view, onFile };
}

function drop(target: HTMLElement, files: File[]) {
  const event = createEvent.drop(target);
  Object.defineProperty(event, "dataTransfer", { value: { files } });
  fireEvent(target, event);
}

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [512, "512 B"],
    [1024, "1 KB"],
    [1536, "1.5 KB"],
    [5 * 1024 * 1024, "5 MB"],
    [50 * 1024 * 1024, "50 MB"],
    [3 * 1024 ** 3, "3 GB"],
    [5 * 1024 ** 4, "5120 GB"],
  ])("formats %d bytes as %s", (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });
});

describe("FileDropzone", () => {
  it("has no accessibility violations in any state", async () => {
    const { container } = render(
      <>
        <FileDropzone label="Default" onFile={jest.fn()} hint="Up to 50 MB" />
        <FileDropzone label="Loading" onFile={jest.fn()} loading loadingFileName="products.csv" />
        <FileDropzone label="Failed" onFile={jest.fn()} error="Upload failed" />
        <FileDropzone label="Disabled" onFile={jest.fn()} disabled />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("is a labelled group with a keyboard reachable file input and a visible label button", () => {
    setup({ hint: "CSV, up to 50 MB" });

    expect(screen.getByRole("group", { name: "Products CSV" })).toBeInTheDocument();
    const input = screen.getByLabelText("Choose a file");
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("accept", ".csv,text/csv");
    expect(input).toHaveAccessibleDescription("CSV, up to 50 MB");
    expect(screen.getByText("or drag and drop it here")).toBeInTheDocument();
  });

  it("hands over the chosen file", async () => {
    const { onFile } = setup();
    const file = csv();

    await userEvent.upload(screen.getByLabelText("Choose a file"), file);

    expect(onFile).toHaveBeenCalledWith(file);
  });

  it("hands over a dropped file and shows the drag state while dragging", () => {
    const { onFile } = setup();
    const group = screen.getByRole("group");

    fireEvent.dragOver(group);
    expect(screen.getByText("Drop the file to select it")).toBeInTheDocument();
    fireEvent.dragLeave(group);
    expect(screen.getByText("or drag and drop it here")).toBeInTheDocument();
    drop(group, [csv()]);

    expect(onFile).toHaveBeenCalledTimes(1);
  });

  it("refuses an empty file, one over the limit and a failing custom check, in plain language", async () => {
    const { onFile } = setup({
      maxBytes: 1024 * 1024,
      validate: (file) => (file.name.endsWith(".csv") ? null : "Choose a .csv file."),
    });
    const input = screen.getByLabelText("Choose a file");

    await userEvent.upload(input, csv("empty.csv", 0));
    expect(screen.getByRole("alert")).toHaveTextContent("The file is empty.");
    expect(input).toBeInvalid();

    await userEvent.upload(input, csv("big.csv", 5 * 1024 * 1024));
    expect(screen.getByRole("alert")).toHaveTextContent("The file is 5 MB, larger than the 1 MB limit.");

    await userEvent.upload(input, csv("data.txt", 10), { applyAccept: false });
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a .csv file.");
    expect(onFile).not.toHaveBeenCalled();
  });

  it("clears the message when a valid file follows", async () => {
    const { onFile } = setup({ maxBytes: 1000 });
    const input = screen.getByLabelText("Choose a file");
    await userEvent.upload(input, csv("big.csv", 5000));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await userEvent.upload(input, csv("ok.csv", 10));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onFile).toHaveBeenCalledTimes(1);
  });

  it("accepts one file at a time", () => {
    const { onFile } = setup();

    drop(screen.getByRole("group"), [csv("a.csv"), csv("b.csv")]);

    expect(screen.getByRole("alert")).toHaveTextContent("Choose one file at a time.");
    expect(onFile).not.toHaveBeenCalled();
  });

  it("ignores an empty drop", () => {
    const { onFile } = setup();

    drop(screen.getByRole("group"), []);

    expect(onFile).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error given by the parent and links it to the input", () => {
    setup({ error: "The server could not be reached" });

    expect(screen.getByRole("alert")).toHaveTextContent("could not be reached");
    expect(screen.getByLabelText("Choose a file")).toHaveAccessibleDescription("The server could not be reached");
  });

  it("is busy while uploading and offers no input", () => {
    setup({ loading: true, loadingFileName: "products.csv" });

    expect(screen.getByRole("group")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Uploading products.csv");
    expect(screen.queryByLabelText("Choose a file")).not.toBeInTheDocument();
  });

  it("says plainly that it is uploading when the name is unknown", () => {
    setup({ loading: true });

    expect(screen.getByRole("status")).toHaveTextContent(/^Uploading$/);
  });

  it("ignores drops and drag highlighting while disabled", () => {
    const { onFile } = setup({ disabled: true });
    const group = screen.getByRole("group");

    fireEvent.dragOver(group);
    drop(group, [csv()]);

    expect(screen.getByLabelText("Choose a file")).toBeDisabled();
    expect(screen.queryByText("Drop the file to select it")).not.toBeInTheDocument();
    expect(onFile).not.toHaveBeenCalled();
  });

  describe("keyboard", () => {
    it("reaches the file input with Tab and shows it as the label's focus target", async () => {
      setup({ hint: "CSV only" });
      const input = screen.getByLabelText("Choose a file");

      await userEvent.tab();

      expect(input).toHaveFocus();
      expect(input).toHaveClass("peer");
      expect(screen.getByText("Choose a file")).toHaveClass("peer-focus-visible:outline-2");
    });

    it.each(["{Enter}", " "])("activates the picker with %j on the focused input", async (key) => {
      setup();
      const input = screen.getByLabelText("Choose a file");
      const opened = jest.fn((event: Event) => {
        event.preventDefault();
      });
      input.addEventListener("click", opened);

      await userEvent.tab();
      await userEvent.keyboard(key);

      expect(opened).toHaveBeenCalledTimes(1);
    });

    it("hands over the file chosen after the keyboard opened the picker", async () => {
      const { onFile } = setup();
      const file = csv();

      await userEvent.tab();
      await userEvent.upload(screen.getByLabelText("Choose a file"), file);

      expect(onFile).toHaveBeenCalledWith(file);
    });

    it("is skipped by Tab while disabled or uploading", async () => {
      const { unmount } = setup({ disabled: true });
      await userEvent.tab();
      expect(screen.getByLabelText("Choose a file")).not.toHaveFocus();
      unmount();

      setup({ loading: true });
      await userEvent.tab();
      expect(document.body).toHaveFocus();
    });
  });

  describe("limits", () => {
    it("refuses an empty file", async () => {
      const { onFile } = setup();

      await userEvent.upload(screen.getByLabelText("Choose a file"), csv("empty.csv", 0));

      expect(screen.getByRole("alert")).toHaveTextContent("The file is empty.");
      expect(onFile).not.toHaveBeenCalled();
    });

    it("refuses a file one byte over the limit but accepts one exactly at it", async () => {
      const { onFile } = setup({ maxBytes: 1000 });
      const input = screen.getByLabelText("Choose a file");

      await userEvent.upload(input, csv("over.csv", 1001));
      expect(screen.getByRole("alert")).toHaveTextContent("larger than the 1000 B limit");
      expect(onFile).not.toHaveBeenCalled();

      await userEvent.upload(input, csv("exact.csv", 1000));
      expect(onFile).toHaveBeenCalledTimes(1);
    });

    it("takes one file from the picker, which has no multiple selection, and refuses several dropped at once", async () => {
      const { onFile } = setup();

      await userEvent.upload(screen.getByLabelText("Choose a file"), [csv("a.csv"), csv("b.csv")]);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();

      drop(screen.getByRole("group"), [csv("a.csv"), csv("b.csv"), csv("c.csv")]);
      expect(screen.getByRole("alert")).toHaveTextContent("Choose one file at a time.");
      expect(onFile).toHaveBeenCalledTimes(1);
    });
  });

  it("has no accessibility violations while showing a rejection", async () => {
    const { container } = setup({ maxBytes: 10 });

    await userEvent.upload(screen.getByLabelText("Choose a file"), csv("big.csv", 50));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
