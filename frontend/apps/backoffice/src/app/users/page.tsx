import type { Metadata } from "next";
import { createLoader } from "nuqs/server";
import { getSession } from "@ecommerce/auth/next";
import { UsersView } from "../../components/users/users-view";
import { userSearchParsers } from "../../lib/user-search";
import { loadUserPage } from "../../server/accounts";
import { isFailure } from "../../server/products";
import { changeUserRoleAction } from "./actions";

export const metadata: Metadata = { title: "Users" };

type UsersPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const loadSearch = createLoader(userSearchParsers);

function toSearchParams(record: Record<string, string | string[] | undefined>): URLSearchParams {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(record)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
      search.append(name, item);
    }
  }
  return search;
}

export default async function UsersPage({ searchParams }: UsersPageProps) {
  const state = loadSearch(toSearchParams(await searchParams));
  const [page, session] = await Promise.all([loadUserPage(state), getSession()]);
  return (
    <section aria-labelledby="users-heading" className="flex flex-col gap-6">
      <h1 id="users-heading" className="text-3xl font-semibold">
        Users
      </h1>
      <UsersView
        page={isFailure(page) ? null : page}
        failure={isFailure(page) ? page : null}
        currentUserId={session?.userId ?? ""}
        changeRole={changeUserRoleAction}
      />
    </section>
  );
}
