import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import AccountPage from "../src/app/account/page";
import { PROFILE } from "./support/api";

const requireSession = jest.fn();
const loadProfile = jest.fn();

jest.mock("@ecommerce/auth/next", () => ({
  requireSession: (options: unknown) => requireSession(options) as unknown,
}));
jest.mock("../src/server/profile", () => ({ loadProfile: () => loadProfile() as unknown }));
jest.mock("../src/app/account/actions", () => ({ updateProfileAction: jest.fn() }));

beforeEach(() => {
  requireSession.mockReset();
  loadProfile.mockReset();
  requireSession.mockResolvedValue({ userId: "u1", email: "token@example.com", role: "customer" });
  loadProfile.mockResolvedValue(PROFILE);
});

describe("account page", () => {
  it("requires a session and shows the profile form with the email", async () => {
    const { container } = render(await AccountPage());

    expect(requireSession).toHaveBeenCalledWith({ loginPath: "/login" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 2, name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("Signed in as ada@example.com.")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Ada Lovelace");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("falls back to the email of the token and then to the user id", async () => {
    loadProfile.mockResolvedValue({ ...PROFILE, email: null });
    const first = render(await AccountPage());
    expect(screen.getByText("Signed in as token@example.com.")).toBeInTheDocument();
    first.unmount();

    requireSession.mockResolvedValue({ userId: "u1", role: "customer" });
    render(await AccountPage());
    expect(screen.getByText("Signed in as u1.")).toBeInTheDocument();
  });

  it("explains a profile that could not be loaded, with a way to retry, and no form", async () => {
    loadProfile.mockResolvedValue({ ok: false, status: 503, title: "Down", fieldErrors: {} });

    const { container } = render(await AccountPage());

    expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/account");
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
