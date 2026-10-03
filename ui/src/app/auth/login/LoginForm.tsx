"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { loginApiV1AuthLoginPost } from "@/client/sdk.gen";
import { AuthEnterpriseCTA } from "@/components/auth/AuthEnterpriseCTA";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiErrorMessage } from "@/i18n/errors";
import { useCopy } from "@/i18n/LocaleProvider";


export function LoginForm({ signupEnabled }: { signupEnabled: boolean }) {
    const copy = useCopy();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const res = await loginApiV1AuthLoginPost({
        body: { email, password },
      });

      if (res.error || !res.data) {
        const detail = apiErrorMessage(res.error, copy);
        toast.error(detail);
        return;
      }

      // Set httpOnly cookies via server route
      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: res.data.token, user: res.data.user }),
      });

      window.location.href = "/after-sign-in";
    } catch {
      toast.error(copy("An error occurred. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell enterpriseSlot={<AuthEnterpriseCTA />}>
      <div className="space-y-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">{copy("Sign in")}</h1>
        <p className="text-sm text-muted-foreground">{copy("Enter your email and password to continue")}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">{copy("Email")}</Label>
          <Input
            id="email"
            type="email"
            placeholder={copy("you@example.com")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">{copy("Password")}</Label>
          <Input
            id="password"
            type="password"
            placeholder={copy("Enter your password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? copy("Signing in...") : copy("Sign in")}
        </Button>
      </form>

      {signupEnabled && (
        <p className="text-center text-sm text-muted-foreground">{copy("Don't have an account?")}{" "}
          <Link href="/auth/signup" className="text-primary underline-offset-4 hover:underline">{copy("Sign up")}</Link>
        </p>
      )}
    </AuthShell>
  );
}
