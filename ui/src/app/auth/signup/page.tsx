"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { signupApiV1AuthSignupPost } from "@/client/sdk.gen";
import { AuthEnterpriseCTA } from "@/components/auth/AuthEnterpriseCTA";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiErrorMessage } from "@/i18n/errors";
import { useCopy } from "@/i18n/LocaleProvider";


export default function SignupPage() {
    const copy = useCopy();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (password.length < 8) {
      toast.error(copy("Password must be at least 8 characters"));
      return;
    }

    if (password !== confirmPassword) {
      toast.error(copy("Passwords do not match"));
      return;
    }

    setLoading(true);

    try {
      const res = await signupApiV1AuthSignupPost({
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
        <h1 className="text-2xl font-semibold tracking-tight">{copy("Create an account")}</h1>
        <p className="text-sm text-muted-foreground">{copy("Enter your details to get started")}</p>
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
            placeholder={copy("At least 8 characters")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirmPassword">{copy("Confirm password")}</Label>
          <Input
            id="confirmPassword"
            type="password"
            placeholder={copy("Confirm your password")}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={8}
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? copy("Creating account...") : copy("Create account")}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">{copy("Already have an account?")}{" "}
        <Link href="/auth/login" className="text-primary underline-offset-4 hover:underline">{copy("Sign in")}</Link>
      </p>
    </AuthShell>
  );
}
