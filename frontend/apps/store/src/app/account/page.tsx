import type { Metadata } from "next";
import { requireSession } from "@ecommerce/auth/next";
import { isFailure } from "@ecommerce/web-core";
import { ProfileForm } from "../../components/account/profile-form";
import { ACCOUNT_PATH, LOGIN_PATH } from "../../lib/paths";
import { loadProfile } from "../../server/profile";
import { updateProfileAction } from "./actions";

export const metadata: Metadata = { title: "My account", robots: { index: false } };

export default async function AccountPage() {
  const session = await requireSession({ loginPath: LOGIN_PATH });
  const profile = await loadProfile();
  return (
    <section aria-labelledby="account-heading" className="flex flex-col gap-6">
      <h1 id="account-heading" className="text-3xl font-semibold">
        My account
      </h1>
      {isFailure(profile) ? (
        <div role="alert" className="flex flex-col items-start gap-3 text-base text-danger-strong">
          <p>Your profile could not be loaded right now. Try again in a moment.</p>
          <a href={ACCOUNT_PATH} className="text-accent-strong underline">
            Try again
          </a>
        </div>
      ) : (
        <>
          <p className="text-base text-secondary">Signed in as {profile.email ?? session.email ?? session.userId}.</p>
          <section aria-labelledby="profile-heading" className="flex flex-col gap-4">
            <h2 id="profile-heading" className="text-xl font-semibold">
              Profile
            </h2>
            <ProfileForm profile={profile} submit={updateProfileAction} />
          </section>
        </>
      )}
    </section>
  );
}
