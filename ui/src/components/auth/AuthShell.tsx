"use client";

// Shared dark two-column auth shell, used by BOTH the Stack Auth handler
// (/handler/[...stack], cloud) and the local/OSS auth pages (/auth/login,
// /auth/signup). LEFT: a centered card that wraps the auth form (`children`).
// RIGHT (lg+ only): a brand/value panel with the Dograh and Abera Cloud logos
// and product proof points. Mobile collapses to the single card column.
// The form column stays usable on short viewports. The palette uses the app's
// blacks and greys with one warm CTA accent.

import type { ReactNode } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { useCopy } from "@/i18n/LocaleProvider";
import { LocaleSwitcher } from "@/i18n/LocaleSwitcher";


const HIGHLIGHTS = [
  "Speech-to-speech",
  "MCP-native",
  "BYOK - any model",
];

export function AuthShell({
  children,
}: {
  children: ReactNode;
}) {
  const copy = useCopy();
  return (
    <div className="grid min-h-screen w-full bg-background lg:grid-cols-[55%_45%]">
      {/* Form column (LEFT) — scrolls and stays centered so tall forms never
          clip. Carries the giant faded "dograh" imprint along its bottom. */}
      <main className="auth-imprint flex min-h-screen flex-col overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-6 sm:p-10">
          <div className="w-full max-w-md space-y-6 rounded-2xl border border-border/60 bg-card p-6 shadow-lg sm:p-8">
            {/* Mobile-only brand lockup (brand panel is hidden) */}
            <div className="lg:hidden">
              <AuthBrandLockup />
            </div>
            <div className="flex justify-end"><LocaleSwitcher /></div>
            {children}
          </div>
        </div>
      </main>

      {/* Brand / value panel (RIGHT) — hidden on mobile */}
      <aside className="relative hidden flex-col justify-between overflow-hidden border-l border-border/60 bg-zinc-950 p-10 lg:flex xl:p-14">
        {/* Ambient depth: soft radial glow behind the content */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 top-1/3 size-[28rem] rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle, var(--cta), transparent 70%)" }}
        />

        <div className="relative">
          <AuthBrandLockup inverse />
        </div>

        <div className="relative flex flex-1 items-center">
          <div className="max-w-md space-y-5">
            <h1 className="text-3xl font-semibold leading-tight tracking-tight text-zinc-50 xl:text-4xl">{copy("The open-source voice AI platform.")}</h1>
            <ul className="flex flex-wrap gap-2">
              {HIGHLIGHTS.map((point) => (
                <li
                  key={copy(point)}
                  className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-zinc-300"
                >
                  {copy(point)}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </aside>
    </div>
  );
}

function AuthBrandLockup({ inverse = false }: { inverse?: boolean }) {
  const copy = useCopy();
  const textClass = inverse ? "text-zinc-100" : "text-foreground";
  const dividerClass = inverse ? "bg-white/20" : "bg-border";

  return (
    <div className="flex items-center gap-3">
      <BrandLogo inverse={inverse} className={inverse ? "h-8" : "h-7"} />
      <span aria-hidden="true" className={`h-6 w-px ${dividerClass}`} />
      <span className="flex items-center gap-2">
        {/* Abera's shared brand mark; the adjacent text identifies this product as Abera Cloud. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/abera-cloud-mark.svg" alt="" className="size-7 rounded-lg" />
        <span className={`text-sm font-semibold tracking-tight ${textClass}`}>{copy("Abera Cloud")}</span>
      </span>
    </div>
  );
}
