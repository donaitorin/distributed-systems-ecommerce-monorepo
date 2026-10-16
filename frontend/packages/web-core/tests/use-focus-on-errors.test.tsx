import { render, screen } from "@testing-library/react";
import { useRef } from "react";
import { useFocusOnErrors } from "../src/client";

const ORDER = ["email", "password"] as const;

function Form({ state }: { state: { fieldErrors?: Partial<Record<string, string>>; error?: string } }) {
  const formRef = useRef<HTMLFormElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  useFocusOnErrors({ formRef, errorRef, state, order: ORDER });
  return (
    <form ref={formRef}>
      <p ref={errorRef} tabIndex={-1}>
        problem
      </p>
      <input name="email" aria-label="email" />
      <input name="password" aria-label="password" />
    </form>
  );
}

describe("useFocusOnErrors", () => {
  it("focuses the first invalid field in the given order", () => {
    render(<Form state={{ fieldErrors: { password: "x", email: "y" } }} />);

    expect(screen.getByLabelText("email")).toHaveFocus();
  });

  it("focuses a later field when only that one is invalid", () => {
    render(<Form state={{ fieldErrors: { password: "x" } }} />);

    expect(screen.getByLabelText("password")).toHaveFocus();
  });

  it("focuses the error message when there is no field error", () => {
    render(<Form state={{ error: "Down" }} />);

    expect(screen.getByText("problem")).toHaveFocus();
  });

  it("moves no focus when there is nothing to report", () => {
    render(<Form state={{}} />);

    expect(document.body).toHaveFocus();
  });
});
