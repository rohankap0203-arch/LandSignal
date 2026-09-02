"use client";

import Link from "next/link";
import { signOut, useSession } from "next-auth/react";

export function AccountMenu() {
  const { data, status } = useSession();

  if (status === "loading") {
    return <div className="account-menu-skeleton" aria-hidden />;
  }

  if (!data?.user) {
    return (
      <div className="account-menu">
        <Link href="/login" className="btn btn-dark text-sm account-signin">
          Sign in
        </Link>
        <Link href="/login?mode=signup" className="btn btn-ghost text-sm account-create">
          Create account
        </Link>
      </div>
    );
  }

  const label = data.user.name || data.user.email || "Account";
  const initial = label.trim().charAt(0).toUpperCase() || "L";

  return (
    <div className="account-menu account-menu-user">
      <Link href="/account" className="account-avatar" title={data.user.email || label} aria-label="Open account">
        {initial}
      </Link>
      <Link href="/account" className="account-user-meta">
        <span className="account-user-name">{label}</span>
        {data.user.email ? <span className="account-user-email">{data.user.email}</span> : null}
      </Link>
      <button
        type="button"
        className="btn btn-ghost text-sm account-signout"
        onClick={() => void signOut({ callbackUrl: "/" })}
      >
        Sign out
      </button>
    </div>
  );
}
