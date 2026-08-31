import Link from "next/link";
import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";

export default async function AccountPage() {
  const session = await auth();
  if (!session?.user) {
    redirect("/login?callbackUrl=/account");
  }

  const name = session.user.name || "LandSignal investor";
  const email = session.user.email || "";

  return (
    <div className="account-page space-y-6">
      <div>
        <h1 className="display text-3xl font-semibold">Your account</h1>
        <p className="mt-1 max-w-xl text-sm text-[var(--muted)]">
          Land Alerts and watchlists are saved to this account when you are signed in.
        </p>
      </div>

      <section className="panel account-card space-y-3 p-5">
        <div className="account-card-row">
          <span className="account-card-label">Name</span>
          <span className="account-card-value">{name}</span>
        </div>
        <div className="account-card-row">
          <span className="account-card-label">Email</span>
          <span className="account-card-value">{email || "—"}</span>
        </div>
        <div className="account-card-row">
          <span className="account-card-label">Account id</span>
          <span className="account-card-value mono text-xs">{session.user.id}</span>
        </div>
      </section>

      <div className="flex flex-wrap gap-3">
        <Link href="/alerts" className="btn btn-dark">
          Open Land Alerts
        </Link>
        <Link href="/watchlist" className="btn btn-ghost">
          Watchlist
        </Link>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/" });
          }}
        >
          <button type="submit" className="btn btn-ghost">
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}
