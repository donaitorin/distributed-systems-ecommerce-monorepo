import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { expect, userEvent, within } from "storybook/test";
import type { Failure } from "../../lib/failure";
import type { RoleChanged } from "../../server/accounts";
import { withAppProviders } from "../story-support";
import { UsersView } from "./users-view";

const ADA = {
  user_id: "11111111-1111-4111-8111-111111111111",
  email: "ada@example.com",
  name: "Ada Lovelace",
  phone: null,
  role: "customer",
  created_at: "2026-10-10T12:00:00Z",
  updated_at: "2026-10-11T12:00:00Z",
};
const ADMIN = { ...ADA, user_id: "22222222-2222-4222-8222-222222222222", email: "admin@example.com", name: null, role: "admin" };
const NEWCOMER = { ...ADA, user_id: "33333333-3333-4333-8333-333333333333", email: null, name: null };

const changed = (): Promise<RoleChanged | Failure> => Promise.resolve({ ok: true, userId: ADA.user_id, role: "admin" });
const refused: () => Promise<RoleChanged | Failure> = () =>
  Promise.resolve({
    ok: false,
    status: 409,
    title: "Cannot change your own role",
    detail: "Ask another admin to change this account's role",
    fieldErrors: {},
  });

const meta = {
  title: "Backoffice/UsersView",
  component: UsersView,
  parameters: { layout: "padded" },
  decorators: [withAppProviders("?role=admin")],
  args: {
    page: { items: [ADA, ADMIN, NEWCOMER], next_cursor: "NEXT" },
    failure: null,
    currentUserId: ADMIN.user_id,
    changeRole: changed,
  },
} satisfies Meta<typeof UsersView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByRole("status")).toHaveTextContent("3 users on this page");
  },
};

export const LastPage: Story = { args: { page: { items: [ADA], next_cursor: null } } };

export const Empty: Story = { args: { page: { items: [], next_cursor: null } } };

export const Failed: Story = {
  args: { page: null, failure: { ok: false, status: 503, title: "Down", fieldErrors: {} } },
};

export const StaleCursor: Story = {
  args: { page: null, failure: { ok: false, status: 422, title: "Invalid", fieldErrors: { cursor: "no match" } } },
};

export const ConfirmRoleChange: Story = {
  play: async ({ canvasElement }) => {
    const table = within(within(canvasElement).getByRole("table", { name: "User list" }));
    await userEvent.click(table.getByRole("button", { name: "Make admin: ada@example.com" }));
    await expect(await within(canvasElement.ownerDocument.body).findByRole("dialog", { name: "Make this user an admin?" })).toBeVisible();
  },
};

export const OwnRoleRefused: Story = {
  args: { changeRole: refused },
  play: async ({ canvasElement }) => {
    const table = within(within(canvasElement).getByRole("table", { name: "User list" }));
    await userEvent.click(table.getByRole("button", { name: "Make customer: admin@example.com" }));
    const body = within(canvasElement.ownerDocument.body);
    await userEvent.click(await body.findByRole("button", { name: "Make customer" }));
    await expect(await body.findByText(/You cannot change your own role/, { selector: "p[role='alert']" })).toBeVisible();
  },
};

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};
