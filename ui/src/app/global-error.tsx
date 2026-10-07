"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect, useState } from "react";

import { DEFAULT_UI_LOCALE, LOCALE_COOKIE, resolveUiLocale } from "@/i18n/config";
import { CopyText,LocaleProvider } from "@/i18n/LocaleProvider";

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  const [locale, setLocale] = useState(DEFAULT_UI_LOCALE);
  useEffect(() => {
    Sentry.captureException(error);
    const cookie = document.cookie.split("; ").find(value => value.startsWith(LOCALE_COOKIE + "="))?.split("=")[1];
    setLocale(resolveUiLocale(cookie, DEFAULT_UI_LOCALE));
  }, [error]);
  return <html lang={locale}><body>
    <LocaleProvider initialLocale={locale} key={locale}>
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
        <h1><CopyText text="Something went wrong" /></h1>
        <p><CopyText text="Something went wrong. Please try again." /></p>
        <button onClick={() => window.location.reload()}><CopyText text="Try again" /></button>
      </main>
    </LocaleProvider>
  </body></html>;
}
