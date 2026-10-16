"use client";

import { useState, useTransition } from "react";
import { useQueryStates } from "nuqs";
import { Button, ConfirmDialog, Input, Select, Table, type SelectOption, type TableColumn } from "@ecommerce/ui";
import { isSessionFailure, type Failure } from "@ecommerce/web-core";
import { roleChangeFailureMessage } from "../../lib/messages";
import { LOGIN_PATH } from "../../lib/paths";
import type { Role, UserPage, UserProfile } from "../../lib/types";
import { useNavigation, useUrlText } from "@ecommerce/web-core/client";
import { hasUserFilters, ROLES, USER_PAGE_SIZES, userSearchParsers } from "../../lib/user-search";
import type { RoleChanged } from "../../server/accounts";
import { useNotify } from "../notifications";

export type UsersViewProps = {
  page: UserPage | null;
  failure: Failure | null;
  currentUserId: string;
  changeRole: (userId: string, role: Role) => Promise<RoleChanged | Failure>;
};

const ANY = "any";
const ROLE_OPTIONS: readonly SelectOption[] = [
  { value: ANY, label: "Any role" },
  ...ROLES.map((role) => ({ value: role, label: role === "admin" ? "Admin" : "Customer" })),
];
const DATE_FORMAT = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" });

function roleLabel(role: string): string {
  return role === "admin" ? "Admin" : role === "customer" ? "Customer" : role;
}

function failureText(failure: Failure): string {
  if (failure.status === 422) {
    return failure.fieldErrors.cursor !== undefined
      ? "This page link no longer matches the current filters."
      : "Some filters are not valid. Adjust them and try again.";
  }
  if (failure.status === 503 || failure.status === null) {
    return "The user list is not available right now. Try again in a moment.";
  }
  return failure.detail ?? failure.title;
}

type Target = { user: UserProfile; role: Role };

export function UsersView({ page, failure, currentUserId, changeRole }: UsersViewProps) {
  const navigation = useNavigation();
  const notify = useNotify();
  const [pending, startTransition] = useTransition();
  const [state, setState] = useQueryStates(userSearchParsers, { history: "push", shallow: false, startTransition });
  const [emailDraft, setEmailDraft] = useUrlText({
    value: state.email,
    commit: (email) => {
      void setState({ email, cursor: null });
    },
  });
  const [overrides, setOverrides] = useState<Readonly<Record<string, Role>>>({});
  const [target, setTarget] = useState<Target | null>(null);
  const [changing, setChanging] = useState(false);
  const [dialogError, setDialogError] = useState<string>();

  const roleOf = (user: UserProfile): string => overrides[user.user_id] ?? user.role;
  const otherRole = (user: UserProfile): Role => (roleOf(user) === "admin" ? "customer" : "admin");
  const name = (user: UserProfile) => user.email ?? user.name ?? "this user";

  const closeDialog = () => {
    setTarget(null);
    setDialogError(undefined);
  };

  const confirm = async () => {
    if (!target) {
      return;
    }
    setChanging(true);
    const result = await changeRole(target.user.user_id, target.role);
    setChanging(false);
    if (result.ok) {
      setOverrides((current) => ({ ...current, [result.userId]: result.role }));
      notify({
        title: "Role changed",
        description: `${name(target.user)} is now ${roleLabel(result.role).toLowerCase()}. The list catches up in a moment.`,
        variant: "success",
      });
      closeDialog();
      return;
    }
    if (isSessionFailure(result)) {
      navigation.push(`${LOGIN_PATH}?reason=expired`);
      return;
    }
    const message = roleChangeFailureMessage(result);
    setDialogError(message);
    notify({ title: "The role was not changed", description: message, variant: "error" });
  };

  const actionButton = (user: UserProfile) => (
    <Button
      variant="secondary"
      aria-label={`${otherRole(user) === "admin" ? "Make admin" : "Make customer"}: ${name(user)}`}
      onClick={() => {
        setDialogError(undefined);
        setTarget({ user, role: otherRole(user) });
      }}
    >
      {otherRole(user) === "admin" ? "Make admin" : "Make customer"}
    </Button>
  );

  const emailCell = (user: UserProfile) => (
    <span className="break-all">
      {user.email ?? "No email yet"}
      {user.user_id === currentUserId ? <span className="text-secondary"> (you)</span> : null}
    </span>
  );

  const columns: readonly TableColumn<UserProfile>[] = [
    { key: "email", header: "Email", cell: emailCell },
    { key: "name", header: "Name", cell: (user) => user.name ?? "Not set" },
    { key: "role", header: "Role", cell: (user) => roleLabel(roleOf(user)) },
    { key: "joined", header: "Joined", cell: (user) => DATE_FORMAT.format(new Date(user.created_at)) },
    { key: "actions", header: "Actions", cell: actionButton },
  ];

  const items = page?.items ?? [];
  const hasMore = Boolean(page?.next_cursor);

  return (
    <div className="flex flex-col gap-6">
      <form
        role="search"
        aria-label="Filter users"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <div className="sm:col-span-2">
          <Input
            label="Email starts with"
            type="search"
            name="email"
            autoComplete="off"
            value={emailDraft}
            onChange={(event) => {
              setEmailDraft(event.target.value);
            }}
          />
        </div>
        <Select
          label="Role"
          options={ROLE_OPTIONS}
          value={state.role ?? ANY}
          onValueChange={(value) => {
            void setState({ role: value === ANY ? null : (value as Role), cursor: null });
          }}
        />
        <Select
          label="Users per page"
          options={USER_PAGE_SIZES.map((size) => ({ value: String(size), label: `${size} per page` }))}
          value={String(state.limit)}
          onValueChange={(value) => {
            void setState({ limit: Number(value), cursor: null });
          }}
        />
        {hasUserFilters(state) ? (
          <div className="sm:col-span-2 lg:col-span-4">
            <Button
              variant="secondary"
              onClick={() => {
                void setState({ email: null, role: null, cursor: null });
              }}
            >
              Clear filters
            </Button>
          </div>
        ) : null}
      </form>
      <div aria-busy={pending} className={pending ? "flex flex-col gap-4 opacity-60" : "flex flex-col gap-4"}>
        <Table
          caption="User list"
          columns={columns}
          rows={items}
          getRowKey={(user) => user.user_id}
          error={failure ? failureText(failure) : undefined}
          emptyMessage="No users match these filters."
          renderCard={(user) => (
            <div className="flex flex-col gap-3">
              <p className="font-medium">{emailCell(user)}</p>
              <p className="text-sm text-secondary">{user.name ?? "Name not set"}</p>
              <p className="text-sm">
                {roleLabel(roleOf(user))}, joined {DATE_FORMAT.format(new Date(user.created_at))}
              </p>
              <div>{actionButton(user)}</div>
            </div>
          )}
        />
        {failure?.fieldErrors.cursor !== undefined ? (
          <div>
            <Button
              variant="secondary"
              onClick={() => {
                void setState({ cursor: null });
              }}
            >
              Back to the first page
            </Button>
          </div>
        ) : null}
        {page ? (
          <nav aria-label="User pages" className="flex flex-wrap items-center justify-between gap-4">
            <p role="status" className="text-sm text-secondary">
              {items.length === 1 ? "1 user on this page" : `${items.length} users on this page`}
              {hasMore ? ", more available" : ""}
            </p>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                disabled={state.cursor === null || pending}
                onClick={() => {
                  void setState({ cursor: null });
                }}
              >
                First page
              </Button>
              <Button
                variant="secondary"
                disabled={!hasMore || pending}
                onClick={() => {
                  void setState({ cursor: page.next_cursor ?? null });
                }}
              >
                Next
              </Button>
            </div>
          </nav>
        ) : null}
      </div>
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) {
            closeDialog();
          }
        }}
        title={target?.role === "admin" ? "Make this user an admin?" : "Make this user a customer?"}
        description={
          target
            ? target.role === "admin"
              ? `${name(target.user)} will be able to manage products, categories and users. Their current session keeps its old role until it refreshes, which takes at most 15 minutes.`
              : `${name(target.user)} will lose access to the backoffice. Their current session keeps its admin role until it refreshes, which takes at most 15 minutes.`
            : undefined
        }
        confirmLabel={target?.role === "admin" ? "Make admin" : "Make customer"}
        variant={target?.role === "admin" ? "primary" : "danger"}
        pending={changing}
        error={dialogError}
        onConfirm={() => {
          void confirm();
        }}
      />
    </div>
  );
}
