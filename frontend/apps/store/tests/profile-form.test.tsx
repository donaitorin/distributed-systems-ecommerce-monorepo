import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { Failure } from "@ecommerce/web-core";
import { ProfileForm } from "../src/components/account/profile-form";
import type { ProfileFormValues } from "../src/lib/account-form";
import type { ProfileSaved } from "../src/server/profile";
import { PROFILE } from "./support/api";
import { settled } from "@ecommerce/web-core/testing";

type Submit = (values: ProfileFormValues) => Promise<ProfileSaved | Failure>;

function setup(result: ProfileSaved | Failure = { ok: true, profile: PROFILE }, profile: { name: string | null; phone: string | null } = { name: PROFILE.name, phone: PROFILE.phone }) {
  const submit = jest.fn<ReturnType<Submit>, Parameters<Submit>>(() => Promise.resolve(result));
  const view = render(<ProfileForm profile={profile} submit={submit} />);
  return { submit, ...view, user: userEvent.setup() };
}

const failure = (status: number | null, fieldErrors: Record<string, string> = {}): Failure => ({
  ok: false,
  status,
  title: "Problem",
  fieldErrors,
});

describe("ProfileForm", () => {
  it("has no accessibility violations and starts with the saved values", async () => {
    const { container } = setup();

    expect(screen.getByLabelText("Name")).toHaveValue("Ada Lovelace");
    expect(screen.getByLabelText("Phone")).toHaveValue("+34600123456");
    expect(screen.getByLabelText("Phone")).toHaveAccessibleDescription(/country code/);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("starts empty for a customer without a profile yet", () => {
    setup(undefined, { name: null, phone: null });

    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Phone")).toHaveValue("");
  });

  it("saves the changes with the keyboard and announces it", async () => {
    const { submit, user } = setup({ ok: true, profile: { ...PROFILE, name: "Ada King" } });

    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Ada King{Enter}");

    await waitFor(() => {
      expect(submit).toHaveBeenCalledWith({ name: "Ada King", phone: "+34600123456" });
    });
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Profile saved.");
    expect(screen.getByLabelText("Name")).toHaveValue("Ada King");
  });

  it("flags an empty name and a bad phone before calling the server and focuses the first one", async () => {
    const { submit, user, container } = setup();

    await user.clear(screen.getByLabelText("Name"));
    await user.clear(screen.getByLabelText("Phone"));
    await user.type(screen.getByLabelText("Phone"), "12");
    await user.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Name")).toHaveFocus();
    });
    expect(screen.getByLabelText("Name")).toBeInvalid();
    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription("Enter your name");
    expect(screen.getByLabelText("Phone")).toHaveAccessibleDescription(/country code/);
    expect(submit).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the server's field errors on the fields and focuses the first", async () => {
    const { user, container } = setup(failure(422, { phone: "Start with + and the country code, like +34 600 123 456." }));

    await user.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Phone")).toHaveFocus();
    });
    expect(screen.getByLabelText("Phone")).toHaveAccessibleDescription(/Start with \+/);
    expect(screen.getByRole("alert")).toHaveTextContent("Some fields need attention");
    expect(screen.queryByText("Profile saved.")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    [429, "Too many requests"],
    [503, "could not be saved"],
    [null, "could not be saved"],
  ])("explains a %s failure and focuses the message", async (status, text) => {
    const { user } = setup(failure(status));

    await user.click(screen.getByRole("button", { name: "Save profile" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(text);
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
  });

  it("clears the saved message when saving again fails", async () => {
    const submit = jest
      .fn<ReturnType<Submit>, Parameters<Submit>>()
      .mockResolvedValueOnce({ ok: true, profile: PROFILE })
      .mockResolvedValueOnce(failure(503));
    render(<ProfileForm profile={PROFILE} submit={submit} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
    await settled();
    await user.type(screen.getByLabelText("Name"), "x");
    await user.click(screen.getByRole("button", { name: "Save profile" }));

    await screen.findByRole("alert");
    expect(screen.queryByText("Profile saved.")).not.toBeInTheDocument();
  });
});
