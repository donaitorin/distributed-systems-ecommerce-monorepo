import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { getNonce } from "get-nonce";
import { Modal } from "../components/modal/modal";
import { Select } from "../components/select/select";
import { StyleNonceProvider, useStyleNonce } from "./style-nonce";

function Probe() {
  return <p>{useStyleNonce() ?? "none"}</p>;
}

afterEach(() => {
  document.head.querySelectorAll("style").forEach((tag) => {
    tag.remove();
  });
});

describe("StyleNonceProvider", () => {
  it("exposes the nonce to descendants and to the style libraries", () => {
    render(
      <StyleNonceProvider nonce="abc123">
        <Probe />
      </StyleNonceProvider>,
    );

    expect(screen.getByText("abc123")).toBeInTheDocument();
    expect(getNonce()).toBe("abc123");
  });

  it("keeps the nonce of the document: a later render with a new request nonce does not replace it", () => {
    const { rerender } = render(
      <StyleNonceProvider nonce="first">
        <Probe />
      </StyleNonceProvider>,
    );
    rerender(
      <StyleNonceProvider nonce="second">
        <Probe />
      </StyleNonceProvider>,
    );

    expect(screen.getByText("first")).toBeInTheDocument();
    expect(getNonce()).toBe("first");
  });

  it("has no nonce by default", () => {
    render(<Probe />);

    expect(screen.getByText("none")).toBeInTheDocument();
  });

  it("stamps the nonce on the style tags a dialog and a select inject", async () => {
    render(
      <StyleNonceProvider nonce="nonce-xyz">
        <Select label="Category" options={[{ value: "a", label: "A" }]} />
        <Modal open title="Dialog" onOpenChange={() => undefined} />
      </StyleNonceProvider>,
    );
    await userEvent.keyboard("{Escape}");

    const tags = [...document.querySelectorAll("style")];
    expect(tags.length).toBeGreaterThan(0);
    expect(tags.every((tag) => tag.nonce === "nonce-xyz" || tag.getAttribute("nonce") === "nonce-xyz")).toBe(true);
  });
});
