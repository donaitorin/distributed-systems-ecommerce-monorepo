import type { Metadata } from "next";
import { getSession } from "@ecommerce/auth/next";
import { redirect } from "next/navigation";
import { LoginForm } from "../../components/login-form";
import { LOGIN_REASON_MESSAGES } from "../../lib/login-form";
import { adminNextPath } from "../../lib/next-path";
import { REQUIRED_ROLE } from "../../lib/paths";
import { signInAction } from "./actions";

export const metadata: Metadata = { title: "Sign in" };

type LoginPageProps = {
  searchParams: Promise<{ reason?: string; next?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { reason, next } = await searchParams;
  const destination = adminNextPath(next);
  const session = await getSession();
  if (session?.role === REQUIRED_ROLE && reason === undefined) {
    redirect(destination);
  }
  const notice = reason === undefined ? undefined : LOGIN_REASON_MESSAGES[reason];
  return (
    <section aria-labelledby="login-heading" className="flex flex-col gap-4">
      <h1 id="login-heading" className="text-3xl font-semibold">
        Administrator sign in
      </h1>
      {notice ? (
        <p role="alert" className="max-w-prose text-base font-medium text-danger-strong">
          {notice}
        </p>
      ) : null}
      <LoginForm action={signInAction} next={destination} />
    </section>
  );
}
