import type { Metadata } from "next";
import { requireSession } from "@ecommerce/auth/next";
import { LOGIN_PATH } from "../../lib/paths";

export const metadata: Metadata = { title: "My account" };

export default async function AccountPage() {
  const session = await requireSession({ loginPath: LOGIN_PATH });
  return (
    <section aria-labelledby="account-heading" className="flex flex-col gap-4">
      <h1 id="account-heading" className="text-3xl font-semibold">
        My account
      </h1>
      <p className="text-base text-secondary">Signed in as {session.email ?? session.userId}.</p>
    </section>
  );
}
