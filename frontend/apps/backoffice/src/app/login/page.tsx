import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign in" };

type LoginPageProps = {
  searchParams: Promise<{ reason?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { reason } = await searchParams;
  return (
    <section aria-labelledby="login-heading" className="flex flex-col gap-4">
      <h1 id="login-heading" className="text-3xl font-semibold">
        Administrator sign in
      </h1>
      {reason === "forbidden" ? (
        <p role="alert" className="max-w-prose text-base font-medium text-danger-strong">
          This account does not have access to the backoffice.
        </p>
      ) : null}
      <p className="max-w-prose text-base text-secondary">Sign in is not available yet.</p>
    </section>
  );
}
