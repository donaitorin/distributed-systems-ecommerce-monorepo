import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { AppShell, MAIN_CONTENT_ID } from "./app-shell";

const NAVIGATION = [
  { label: "Products", href: "/products" },
  { label: "Account", href: "/account" },
];

function renderShell(props: Partial<Parameters<typeof AppShell>[0]> = {}) {
  return render(
    <AppShell brand={{ label: "Store", href: "/" }} navigation={NAVIGATION} footer="Footer text" {...props}>
      <h1>Welcome</h1>
    </AppShell>,
  );
}

describe("AppShell", () => {
  it("has no accessibility violations", async () => {
    const { container } = renderShell();

    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers a skip link as the first focusable element, pointing at the main landmark", () => {
    renderShell();
    const skip = screen.getByRole("link", { name: "Skip to content" });

    expect(skip).toHaveAttribute("href", `#${MAIN_CONTENT_ID}`);
    expect(screen.getAllByRole("link")[0]).toBe(skip);
    expect(screen.getByRole("main")).toHaveAttribute("id", MAIN_CONTENT_ID);
  });

  it("has banner, navigation, main and contentinfo landmarks", () => {
    renderShell();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Footer text");
  });

  it("lists the navigation links", () => {
    renderShell();
    const navigation = screen.getByRole("navigation");

    expect(within(navigation).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/products",
      "/account",
    ]);
  });

  it("labels the navigation as given", () => {
    renderShell({ navigationLabel: "Admin" });

    expect(screen.getByRole("navigation", { name: "Admin" })).toBeInTheDocument();
  });

  it("omits the navigation landmark when there are no links", () => {
    renderShell({ navigation: [] });

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("links the brand to its home page", () => {
    renderShell({ brand: { label: "Backoffice", href: "/admin" } });

    expect(screen.getByRole("link", { name: "Backoffice" })).toHaveAttribute("href", "/admin");
  });

  it("renders the page content inside main", () => {
    renderShell();

    expect(within(screen.getByRole("main")).getByRole("heading", { name: "Welcome" })).toBeInTheDocument();
  });
});
