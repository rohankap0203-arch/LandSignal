import { Suspense } from "react";
import { authProviders } from "@/auth";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="auth-page" />}>
      <LoginForm googleLive={authProviders.googleLive} appleLive={authProviders.appleLive} />
    </Suspense>
  );
}
