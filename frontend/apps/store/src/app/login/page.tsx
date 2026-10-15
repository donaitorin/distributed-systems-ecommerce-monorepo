import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <section aria-labelledby="login-heading" className="flex flex-col gap-4">
      <h1 id="login-heading" className="text-3xl font-semibold">
        Sign in
      </h1>
      <p className="max-w-prose text-base text-secondary">Sign in is not available yet.</p>
    </section>
  );
}
