import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QuantityControl } from "../src/components/cart/quantity-control";

function setup(value = 2, props: Partial<Parameters<typeof QuantityControl>[0]> = {}) {
  const onChange = jest.fn();
  const view = render(<QuantityControl name="Running shoes" value={value} onChange={onChange} {...props} />);
  return { onChange, ...view };
}

const input = () => screen.getByRole("textbox", { name: "Quantity of Running shoes" });

describe("QuantityControl", () => {
  it("is a labelled group with an input and two step buttons, with no accessibility violations", async () => {
    const { container } = setup();

    expect(screen.getByRole("group", { name: "Quantity of Running shoes" })).toBeInTheDocument();
    expect(input()).toHaveValue("2");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("steps up and down", async () => {
    const { onChange } = setup(5);

    await userEvent.click(screen.getByRole("button", { name: "Increase quantity of Running shoes" }));
    await userEvent.click(screen.getByRole("button", { name: "Decrease quantity of Running shoes" }));

    expect(onChange.mock.calls).toEqual([[6], [4]]);
  });

  it("stops at the limits", () => {
    const low = setup(1);
    expect(screen.getByRole("button", { name: "Decrease quantity of Running shoes" })).toBeDisabled();
    low.unmount();

    setup(99);
    expect(screen.getByRole("button", { name: "Increase quantity of Running shoes" })).toBeDisabled();
  });

  it("respects a lower maximum, such as the stock", async () => {
    const { onChange } = setup(3, { max: 3 });

    expect(screen.getByRole("button", { name: "Increase quantity of Running shoes" })).toBeDisabled();
    await userEvent.clear(input());
    await userEvent.type(input(), "4{Enter}");

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a whole number from 1 to 3.");
  });

  it("commits a typed number with Enter and on blur, only when it changed", async () => {
    const { onChange } = setup(2);

    await userEvent.clear(input());
    await userEvent.type(input(), "7{Enter}");
    await userEvent.clear(input());
    await userEvent.type(input(), "9");
    await userEvent.tab();
    await userEvent.clear(input());
    await userEvent.type(input(), "2{Enter}");

    expect(onChange.mock.calls).toEqual([[7], [9]]);
  });

  it.each(["0", "100", "abc", "", "1.5"])("refuses %j with a message tied to the input", async (text) => {
    const { onChange } = setup(2);

    await userEvent.clear(input());
    if (text) {
      await userEvent.type(input(), text);
    }
    await userEvent.tab();

    expect(onChange).not.toHaveBeenCalled();
    expect(input()).toBeInvalid();
    expect(input()).toHaveAccessibleDescription("Enter a whole number from 1 to 99.");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("clears the message when typing again and when the value changes from outside", async () => {
    const { rerender } = setup(2);
    await userEvent.clear(input());
    await userEvent.type(input(), "x");
    await userEvent.tab();
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await userEvent.type(input(), "1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await userEvent.tab();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    rerender(<QuantityControl name="Running shoes" value={4} onChange={jest.fn()} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(input()).toHaveValue("4");
  });

  it("is fully usable with the keyboard", async () => {
    const { onChange } = setup(2);

    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Decrease quantity of Running shoes" })).toHaveFocus();
    await userEvent.tab();
    expect(input()).toHaveFocus();
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");

    expect(onChange).toHaveBeenCalledWith(3);
  });

  it("disables everything while busy", () => {
    setup(2, { disabled: true });

    expect(input()).toBeDisabled();
    expect(screen.getAllByRole("button").every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
  });
});
