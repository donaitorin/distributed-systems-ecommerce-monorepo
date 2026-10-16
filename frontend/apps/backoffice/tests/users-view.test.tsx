import { act, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import type { UrlUpdateEvent } from "nuqs/adapters/testing";
import { UsersView, type UsersViewProps } from "../src/components/users/users-view";
import type { Failure } from "../src/lib/failure";
import { profile } from "./support/api";
import { resetRouter, router } from "./support/navigation-mock";
import { renderApp } from "./support/render";

jest.mock("next/navigation", () => jest.requireActual("./support/navigation-mock") as unknown);

const ADA = profile();
const GRACE = profile({ user_id: "22222222-2222-4222-8222-222222222222", email: "grace@example.com", name: null, role: "admin" });
const NEW = profile({ user_id: "33333333-3333-4333-8333-333333333333", email: null, name: null });
const ME = GRACE.user_id;

function props(overrides: Partial<UsersViewProps> = {}): UsersViewProps {
  return {
    page: { items: [ADA, GRACE, NEW], next_cursor: "NEXT" },
    failure: null,
    currentUserId: ME,
    changeRole: jest.fn().mockResolvedValue({ ok: true, userId: ADA.user_id, role: "admin" }),
    ...overrides,
  };
}

function lastUrl(onUrlUpdate: jest.Mock<void, [UrlUpdateEvent]>): URLSearchParams {
  return onUrlUpdate.mock.lastCall?.[0].searchParams ?? new URLSearchParams();
}

function failure(status: number | null, extra: object = {}): Failure {
  return { ok: false, status, title: "Problem", fieldErrors: {}, ...extra };
}

beforeEach(() => {
  resetRouter();
});

describe("UsersView list", () => {
  it("shows users with role as text, the current user marked, and has no accessibility violations", async () => {
    const { container } = renderApp(<UsersView {...props()} />);
    const table = screen.getByRole("table", { name: "User list" });

    expect(within(table).getByText("ada@example.com")).toBeInTheDocument();
    expect(within(table).getByText("(you)")).toBeInTheDocument();
    expect(within(table).getByText("No email yet")).toBeInTheDocument();
    expect(within(table).getAllByText("Not set")).toHaveLength(2);
    expect(within(table).getAllByText("Admin")).toHaveLength(1);
    expect(within(table).getAllByText("Customer")).toHaveLength(2);
    expect(within(table).getAllByText("Oct 10, 2026").length).toBe(3);
    expect(within(screen.getByRole("list", { name: "User list" })).getAllByRole("listitem")).toHaveLength(3);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("announces how many users are on the page", () => {
    const { unmount } = renderApp(<UsersView {...props()} />);
    expect(screen.getByRole("status")).toHaveTextContent("3 users on this page, more available");
    unmount();

    renderApp(<UsersView {...props({ page: { items: [ADA], next_cursor: null } })} />);
    expect(screen.getByRole("status")).toHaveTextContent("1 user on this page");
    expect(screen.getByRole("status")).not.toHaveTextContent("more available");
  });

  it("shows the empty message", () => {
    renderApp(<UsersView {...props({ page: { items: [], next_cursor: null } })} />);

    expect(within(screen.getByRole("table")).getByText("No users match these filters.")).toBeInTheDocument();
  });

  it.each([
    [failure(503), "not available right now"],
    [failure(null), "not available right now"],
    [failure(422, { fieldErrors: { email: "bad" } }), "filters are not valid"],
    [failure(500, { detail: "Broke" }), "Broke"],
    [failure(500), "Problem"],
  ])("shows a failed load as an alert: %j", (error, text) => {
    renderApp(<UsersView {...props({ page: null, failure: error })} />);

    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByRole("navigation", { name: "User pages" })).not.toBeInTheDocument();
  });
});

describe("UsersView URL state", () => {
  it("reads the filters from the URL and ignores invalid values", () => {
    renderApp(<UsersView {...props()} />, { searchParams: "?email=ada&role=root&limit=100" });

    expect(screen.getByLabelText("Email starts with")).toHaveValue("ada");
    expect(screen.getByRole("combobox", { name: "Role" })).toHaveTextContent("Any role");
    expect(screen.getByRole("combobox", { name: "Users per page" })).toHaveTextContent("100 per page");
  });

  it("writes the role to the URL and clears the cursor", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<UsersView {...props()} />, { searchParams: "?cursor=OLD&email=a", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Role" }));
    await user.click(await screen.findByRole("option", { name: "Admin" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("role")).toBe("admin");
    });
    expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    expect(lastUrl(onUrlUpdate).get("email")).toBe("a");
    expect(onUrlUpdate.mock.lastCall?.[0].options.history).toBe("push");
  });

  it("does not write the default page size, and writes another one", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<UsersView {...props()} />, { searchParams: "?limit=50", onUrlUpdate });

    await user.click(screen.getByRole("combobox", { name: "Users per page" }));
    await user.click(await screen.findByRole("option", { name: "25 per page" }));
    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect(lastUrl(onUrlUpdate).has("limit")).toBe(false);

    await user.click(screen.getByRole("combobox", { name: "Users per page" }));
    await user.click(await screen.findByRole("option", { name: "100 per page" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("limit")).toBe("100");
    });
  });

  it("applies the email prefix 300 ms after the last keystroke", async () => {
    jest.useFakeTimers();
    try {
      const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
      const { user } = renderApp(<UsersView {...props()} />, { searchParams: "?cursor=OLD", onUrlUpdate, fakeTimers: true });

      await user.type(screen.getByLabelText("Email starts with"), "gra");
      act(() => {
        jest.advanceTimersByTime(299);
      });
      expect(onUrlUpdate).not.toHaveBeenCalled();
      act(() => {
        jest.advanceTimersByTime(1);
      });

      await waitFor(() => {
        expect(lastUrl(onUrlUpdate).get("email")).toBe("gra");
      });
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    } finally {
      jest.useRealTimers();
    }
  });

  it("clears the filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<UsersView {...props()} />, { searchParams: "?email=a&role=admin&cursor=C", onUrlUpdate });

    await user.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(() => {
      expect(onUrlUpdate).toHaveBeenCalled();
    });
    expect([...lastUrl(onUrlUpdate).keys()]).toEqual([]);
  });

  it("offers no clear button without filters", () => {
    renderApp(<UsersView {...props()} />, { searchParams: "?limit=50" });

    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });
});

describe("UsersView pagination", () => {
  it("moves forward with the cursor and back to the first page", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(<UsersView {...props()} />, { searchParams: "?role=admin", onUrlUpdate });
    expect(screen.getByRole("button", { name: "First page" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).get("cursor")).toBe("NEXT");
    });
    expect(lastUrl(onUrlUpdate).get("role")).toBe("admin");

    await user.click(screen.getByRole("button", { name: "First page" }));
    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    });
  });

  it("disables Next on the last page", () => {
    renderApp(<UsersView {...props({ page: { items: [ADA], next_cursor: null } })} />, { searchParams: "?cursor=C" });

    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "First page" })).toBeEnabled();
  });

  it("offers to go back when a pasted cursor does not match the filters", async () => {
    const onUrlUpdate = jest.fn<void, [UrlUpdateEvent]>();
    const { user } = renderApp(
      <UsersView {...props({ page: null, failure: failure(422, { fieldErrors: { cursor: "no match" } }) })} />,
      { searchParams: "?cursor=STALE&role=admin", onUrlUpdate },
    );

    expect(within(screen.getByRole("table")).getByRole("alert")).toHaveTextContent("no longer matches");
    await user.click(screen.getByRole("button", { name: "Back to the first page" }));

    await waitFor(() => {
      expect(lastUrl(onUrlUpdate).has("cursor")).toBe(false);
    });
  });
});

describe("UsersView role change", () => {
  function table() {
    return within(screen.getByRole("table", { name: "User list" }));
  }

  it("asks for confirmation, explains the session delay, then changes the role and shows it", async () => {
    const changeRole = jest.fn().mockResolvedValue({ ok: true, userId: ADA.user_id, role: "admin" });
    const { user } = renderApp(<UsersView {...props({ changeRole })} />);

    await user.click(table().getByRole("button", { name: "Make admin: ada@example.com" }));
    const dialog = await screen.findByRole("dialog", { name: "Make this user an admin?" });
    expect(dialog).toHaveAccessibleDescription(expect.stringContaining("at most 15 minutes"));
    expect(changeRole).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Make admin" }));

    await waitFor(() => {
      expect(changeRole).toHaveBeenCalledWith(ADA.user_id, "admin");
    });
    expect(await screen.findByText(/ada@example.com is now admin/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(table().getByRole("button", { name: "Make customer: ada@example.com" })).toBeInTheDocument();
    expect(table().getAllByText("Admin")).toHaveLength(2);
  });

  it("demotes an admin with a danger confirmation", async () => {
    const changeRole = jest.fn().mockResolvedValue({ ok: true, userId: GRACE.user_id, role: "customer" });
    const { user } = renderApp(<UsersView {...props({ changeRole, currentUserId: "someone-else" })} />);

    await user.click(table().getByRole("button", { name: "Make customer: grace@example.com" }));
    const dialog = await screen.findByRole("dialog", { name: "Make this user a customer?" });
    expect(dialog).toHaveAccessibleDescription(expect.stringContaining("lose access to the backoffice"));
    await user.click(within(dialog).getByRole("button", { name: "Make customer" }));

    await waitFor(() => {
      expect(changeRole).toHaveBeenCalledWith(GRACE.user_id, "customer");
    });
  });

  it("shows the API's refusal to change your own role inside the dialog", async () => {
    const changeRole = jest.fn().mockResolvedValue(failure(409, { detail: "Ask another admin to change this account's role" }));
    const { user } = renderApp(<UsersView {...props({ changeRole })} />);

    await user.click(table().getByRole("button", { name: "Make customer: grace@example.com" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Make customer" }));

    const alert = await within(screen.getByRole("dialog")).findByRole("alert");
    expect(alert).toHaveTextContent("You cannot change your own role");
    expect(alert).toHaveTextContent("Ask another admin");
    expect(within(screen.getByRole("table", { name: "User list", hidden: true })).getAllByText("Admin")).toHaveLength(1);
  });

  it("explains a user that no longer exists, and cancelling clears the error", async () => {
    const changeRole = jest.fn().mockResolvedValue(failure(404));
    const { user } = renderApp(<UsersView {...props({ changeRole })} />);

    await user.click(table().getByRole("button", { name: "Make admin: ada@example.com" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Make admin" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("no longer exists");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    await user.click(table().getByRole("button", { name: "Make admin: ada@example.com" }));
    expect(within(await screen.findByRole("dialog")).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("names a user without an email by their name, or generically", async () => {
    const { user } = renderApp(<UsersView {...props({ page: { items: [profile({ email: null }), NEW], next_cursor: null } })} />);

    await user.click(table().getByRole("button", { name: "Make admin: Ada Lovelace" }));
    expect(await screen.findByRole("dialog")).toHaveAccessibleDescription(expect.stringContaining("Ada Lovelace will be able"));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    await user.click(table().getByRole("button", { name: "Make admin: this user" }));
    expect(await screen.findByRole("dialog")).toHaveAccessibleDescription(expect.stringContaining("this user will be able"));
  });

  it("can start from a card as well", async () => {
    const { user } = renderApp(<UsersView {...props()} />);

    await user.click(within(screen.getByRole("list", { name: "User list" })).getByRole("button", { name: "Make admin: ada@example.com" }));

    expect(await screen.findByRole("dialog", { name: "Make this user an admin?" })).toBeInTheDocument();
  });

  it("sends an expired session to the login page", async () => {
    const changeRole = jest.fn().mockResolvedValue(failure(401));
    const { user } = renderApp(<UsersView {...props({ changeRole })} />);

    await user.click(table().getByRole("button", { name: "Make admin: ada@example.com" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Make admin" }));

    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/login?reason=expired");
    });
  });
});
