import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useUrlText } from "../src/lib/use-url-text";

function Field({
  value,
  commit,
  accept,
}: {
  value: string | null;
  commit: (next: string | null) => void;
  accept?: (text: string) => boolean;
}) {
  const [draft, setDraft] = useUrlText({ value, commit, accept });
  return (
    <input
      aria-label="field"
      value={draft}
      onChange={(event) => {
        setDraft(event.target.value);
      }}
    />
  );
}

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

describe("useUrlText", () => {
  it("shows what is typed at once and commits once, 300 ms after the last keystroke", async () => {
    const commit = jest.fn();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    render(<Field value={null} commit={commit} />);

    await user.type(screen.getByLabelText("field"), "shoes");
    expect(screen.getByLabelText("field")).toHaveValue("shoes");
    act(() => {
      jest.advanceTimersByTime(299);
    });
    expect(commit).not.toHaveBeenCalled();
    act(() => {
      jest.advanceTimersByTime(1);
    });

    expect(commit).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith("shoes");
  });

  it("commits null when the field is cleared", async () => {
    const commit = jest.fn();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    render(<Field value="old" commit={commit} />);

    await user.clear(screen.getByLabelText("field"));
    act(() => {
      jest.advanceTimersByTime(300);
    });

    expect(commit).toHaveBeenCalledWith(null);
  });

  it("does not commit a value it was given or one that is not acceptable", async () => {
    const commit = jest.fn();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    render(<Field value="12" commit={commit} accept={(text) => /^\d+$/.test(text)} />);
    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(commit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("field"), "x");
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    expect(commit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("field")).toHaveValue("12x");
  });

  it("follows the URL when it changes from outside, as back and forward do", () => {
    const commit = jest.fn();
    const { rerender } = render(<Field value="shoes" commit={commit} />);

    rerender(<Field value="boots" commit={commit} />);
    expect(screen.getByLabelText("field")).toHaveValue("boots");

    rerender(<Field value={null} commit={commit} />);
    expect(screen.getByLabelText("field")).toHaveValue("");
    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(commit).not.toHaveBeenCalled();
  });

  it("keeps newer typing when its own commit comes back through the URL", async () => {
    const commit = jest.fn();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    const { rerender } = render(<Field value={null} commit={commit} />);

    await user.type(screen.getByLabelText("field"), "ab");
    act(() => {
      jest.advanceTimersByTime(300);
    });
    await user.type(screen.getByLabelText("field"), "c");
    rerender(<Field value="ab" commit={commit} />);

    expect(screen.getByLabelText("field")).toHaveValue("abc");
  });
});
