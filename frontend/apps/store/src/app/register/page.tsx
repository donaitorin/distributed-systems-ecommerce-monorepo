import type { Metadata } from "next";
import { getSession } from "@ecommerce/auth/next";
import { redirect } from "next/navigation";
import { RegisterForm } from "../../components/auth/register-form";
import { authPageHref, LOGIN_PATH, storeNextPath } from "../../lib/paths";
import { registerAction } from "./actions";

export const metadata: Metadata = { title: "Create an account", robots: { index: false } };

type RegisterPageProps = {
  searchParams: Promise<{ next?: string }>;
};

export default async function RegisterPage({ searchParams }: RegisterPageProps) {
  const destination = storeNextPath((await searchParams).next);
  if (await getSession()) {
    redirect(destination);
  }
  return (
    <section aria-labelledby="register-heading" className="flex flex-col gap-4">
      <h1 id="register-heading" className="text-3xl font-semibold">
        Create an account
      </h1>
      <RegisterForm action={registerAction} next={destination} />
      <p className="text-base">
        Already have an account?{" "}
        <a href={authPageHref(LOGIN_PATH, destination)} className="text-accent-strong underline">
          Sign in
        </a>
      </p>
    </section>
  );
}
