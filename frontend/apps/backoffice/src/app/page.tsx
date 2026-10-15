import { getSession } from "@ecommerce/auth/next";

export default async function DashboardPage() {
  const session = await getSession();
  return (
    <section aria-labelledby="dashboard-heading" className="flex flex-col gap-4">
      <h1 id="dashboard-heading" className="text-3xl font-semibold">
        Backoffice
      </h1>
      <p className="max-w-prose text-base text-secondary">
        Signed in as {session?.email ?? session?.userId ?? "an administrator"}. Product and import
        tools will appear here.
      </p>
    </section>
  );
}
