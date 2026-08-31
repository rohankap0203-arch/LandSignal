"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { FormEvent, useMemo, useState } from "react";
import { MapPinMark } from "@/components/map-pin-mark";

type Mode = "signin" | "signup";

function GoogleGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="#EA4335"
        d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.3 14.6 2.4 12 2.4 6.9 2.4 2.8 6.5 2.8 11.6S6.9 20.8 12 20.8c5.2 0 8.6-3.6 8.6-8.7 0-.6-.1-1-.2-1.5H12z"
      />
    </svg>
  );
}

function AppleGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="currentColor"
        d="M16.4 12.6c0-2.1 1.7-3.1 1.8-3.2-1-1.4-2.5-1.6-3-1.7-1.3-.1-2.5.8-3.1.8-.6 0-1.6-.7-2.7-.7-1.4 0-2.7.8-3.4 2.1-1.5 2.5-.4 6.2 1 8.2.7 1 1.5 2.1 2.6 2.1 1 0 1.4-.7 2.7-.7s1.6.7 2.7.7c1.1 0 1.8-1 2.5-2 .8-1.1 1.1-2.2 1.1-2.3 0-.1-2.1-.8-2.2-3.3zM14.6 6.4c.6-.7 1-1.7.9-2.7-.9 0-1.9.6-2.5 1.3-.6.6-1 1.6-.9 2.6 1 0 1.9-.5 2.5-1.2z"
      />
    </svg>
  );
}

export function LoginForm({
  googleLive,
  appleLive,
}: {
  googleLive: boolean;
  appleLive: boolean;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") || "/alerts";
  const initialMode = params.get("mode") === "signup" ? "signup" : "signin";
  const authError = params.get("error");

  const [mode, setMode] = useState<Mode>(initialMode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(
    authError ? "Sign-in was cancelled or failed. Try again." : "",
  );

  const title = useMemo(
    () => (mode === "signup" ? "Create your account" : "Welcome back"),
    [mode],
  );
  const subtitle = useMemo(
    () =>
      mode === "signup"
        ? "Save Land Alerts, watchlists, and acquisition preferences to your account."
        : "Sign in to pick up your matches, saved land, and alert profile.",
    [mode],
  );

  async function finishSession() {
    router.push(callbackUrl);
    router.refresh();
  }

  async function onEmailSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy("credentials");
    try {
      if (mode === "signup") {
        if (!name.trim()) {
          setError("Enter your name.");
          return;
        }
        if (password !== confirm) {
          setError("Passwords do not match.");
          return;
        }
        const reg = await fetch("/api/account/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, name }),
        });
        const payload = (await reg.json().catch(() => ({}))) as { detail?: string };
        if (!reg.ok) {
          setError(payload.detail || "Could not create that account.");
          return;
        }
      }

      const res = await signIn("credentials", {
        email,
        password,
        name,
        mode: "signin",
        redirect: false,
        callbackUrl,
      });
      if (res?.error) {
        setError(
          mode === "signup"
            ? "Account created, but sign-in failed. Try signing in."
            : "Incorrect email or password.",
        );
        return;
      }
      await finishSession();
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  async function onSocial(provider: "google" | "apple") {
    setError("");
    setBusy(provider);
    try {
      const live = provider === "google" ? googleLive : appleLive;
      if (live) {
        await signIn(provider, { callbackUrl, redirect: true });
        return;
      }
      const res = await signIn(provider, {
        redirect: false,
        callbackUrl,
        email: provider === "google" ? "investor@gmail.com" : "investor@icloud.com",
        name: provider === "google" ? "Google Investor" : "Apple Investor",
      });
      if (res?.error) {
        setError(`Could not continue with ${provider === "google" ? "Google" : "Apple"}.`);
        return;
      }
      await finishSession();
    } catch {
      setError(`Could not continue with ${provider === "google" ? "Google" : "Apple"}.`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-panel">
        <Link href="/" className="auth-brand">
          <MapPinMark className="auth-brand-mark" />
          <span>LandSignal</span>
        </Link>

        <div className="auth-tabs" role="tablist" aria-label="Account">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signin"}
            className={mode === "signin" ? "on" : undefined}
            onClick={() => {
              setMode("signin");
              setError("");
            }}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signup"}
            className={mode === "signup" ? "on" : undefined}
            onClick={() => {
              setMode("signup");
              setError("");
            }}
          >
            Create account
          </button>
        </div>

        <h1 className="auth-title">{title}</h1>
        <p className="auth-sub">{subtitle}</p>

        <div className="auth-social">
          <button
            type="button"
            className="auth-social-btn"
            disabled={Boolean(busy)}
            onClick={() => void onSocial("google")}
          >
            <GoogleGlyph />
            <span>{busy === "google" ? "Connecting…" : "Continue with Google"}</span>
          </button>
          <button
            type="button"
            className="auth-social-btn auth-social-apple"
            disabled={Boolean(busy)}
            onClick={() => void onSocial("apple")}
          >
            <AppleGlyph />
            <span>{busy === "apple" ? "Connecting…" : "Continue with Apple"}</span>
          </button>
        </div>

        <div className="auth-divider" aria-hidden>
          <span>or use email</span>
        </div>

        <form className="auth-form" onSubmit={(e) => void onEmailSubmit(e)}>
          {mode === "signup" ? (
            <label className="auth-field">
              <span>Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                placeholder="Your name"
                required
              />
            </label>
          ) : null}
          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              placeholder="you@firm.com"
            />
          </label>
          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              placeholder={mode === "signup" ? "At least 8 characters" : "Your password"}
            />
          </label>
          {mode === "signup" ? (
            <label className="auth-field">
              <span>Confirm password</span>
              <input
                type="password"
                required
                minLength={8}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                placeholder="Re-enter password"
              />
            </label>
          ) : null}

          {error ? <div className="auth-error">{error}</div> : null}

          <button type="submit" className="btn btn-primary auth-submit" disabled={Boolean(busy)}>
            {busy === "credentials"
              ? mode === "signup"
                ? "Creating…"
                : "Signing in…"
              : mode === "signup"
                ? "Create account"
                : "Sign in"}
          </button>
        </form>

        <p className="auth-footnote">
          By continuing you agree to use LandSignal for personal land research.{" "}
          <Link href="/">Back to search</Link>
        </p>
      </div>
    </div>
  );
}
