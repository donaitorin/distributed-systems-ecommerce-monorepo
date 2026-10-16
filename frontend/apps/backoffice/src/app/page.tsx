import { getSession } from "@ecommerce/auth/next";
import { ButtonLink } from "@ecommerce/ui";

export default async function DashboardPage() {
  const session = await getSession();
  return (
    <section aria-labelledby="dashboard-heading" className="flex flex-col gap-4">
      <h1 id="dashboard-heading" className="text-3xl font-semibold">
        Backoffice
      </h1>
      <p className="max-w-prose text-base text-secondary">
        Signed in as {session?.email ?? session?.userId ?? "an administrator"}. Manage the catalog from
        the products page.
      </p>
      <div>
        <ButtonLink href="/admin/products">Go to products</ButtonLink>
      </div>
    </section>
  );
}
