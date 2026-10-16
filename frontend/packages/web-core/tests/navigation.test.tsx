import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NavigationProvider, useNavigation } from "../src/client";
import { resetRouter, router } from "./support/navigation-mock";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

function Buttons() {
  const navigation = useNavigation();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          navigation.push("/products");
        }}
      >
        Go
      </button>
      <button
        type="button"
        onClick={() => {
          navigation.refresh();
        }}
      >
        Refresh
      </button>
    </>
  );
}

beforeEach(() => {
  resetRouter();
});

describe("NavigationProvider", () => {
  it("hands the app router to the components", async () => {
    render(
      <NavigationProvider>
        <Buttons />
      </NavigationProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(router.push).toHaveBeenCalledWith("/products");
    expect(router.refresh).toHaveBeenCalledTimes(1);
  });

  it("is harmless without a provider", async () => {
    render(<Buttons />);

    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(router.push).not.toHaveBeenCalled();
  });
});
