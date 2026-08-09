import { Suspense } from "react";
import { authProviders } from "@/auth";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="auth-page" />}>
      <LoginForm googleProvider={authProviders.google} appleProvider={authProviders.apple} />
    </Suspense>
  );
}
