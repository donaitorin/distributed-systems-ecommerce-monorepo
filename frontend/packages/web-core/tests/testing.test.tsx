import { render, screen } from "@testing-library/react";
import { useEffect, useState } from "react";
import { pendingElements, settled } from "../src/testing";

function Busy({ delay }: { delay: number }) {
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => {
      setBusy(false);
    }, delay);
    return () => {
      clearTimeout(timer);
    };
  }, [delay]);
  return (
    <section aria-label="Results" aria-busy={busy}>
      <button disabled={busy}>Next</button>
    </section>
  );
}

describe("settled", () => {
  it("lists the elements marked as busy and ignores aria-busy=false", () => {
    render(
      <div>
        <p aria-busy="true">a</p>
        <p aria-busy="false">b</p>
        <p>c</p>
      </div>,
    );

    expect(pendingElements().map((element) => element.textContent)).toEqual(["a"]);
  });

  it("resolves at once when nothing is pending", async () => {
    render(<p aria-busy="false">idle</p>);

    await expect(settled()).resolves.toBeUndefined();
  });

  it("waits until the pending state clears, so the next action cannot land on a disabled control", async () => {
    render(<Busy delay={80} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    await settled();

    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("can be limited to a part of the page", async () => {
    render(
      <div>
        <p aria-busy="true">elsewhere</p>
        <section aria-label="Area">
          <p aria-busy="false">idle</p>
        </section>
      </div>,
    );

    await expect(settled(screen.getByRole("region", { name: "Area" }))).resolves.toBeUndefined();
  });

  it("fails with the elements that are still pending when it is never reached", async () => {
    render(<p aria-busy="true">stuck</p>);

    await expect(settled()).rejects.toThrow(/still pending: <p aria-busy="true">stuck<\/p>/);
  }, 10000);
});
