"use client";

import { NextIntlClientProvider } from "next-intl";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { type Copy, copyFor, messagesFor } from "./catalog";
import { isUiLocale, LOCALE_COOKIE, type UiLocale } from "./config";

// Standalone components and existing tests retain the English source language.
// The application root always supplies the locale resolved for this request.
type LocaleContextValue = {
  locale: UiLocale;
  copy: Copy;
  setLocale: (locale: UiLocale) => void;
};

const LocaleContext = createContext<LocaleContextValue>({
  locale: "en",
  copy: copyFor("en"),
  setLocale: () => {},
});

export function LocaleProvider({ initialLocale, children }: {
  initialLocale: UiLocale;
  children: ReactNode;
}) {
  const [locale, setCurrentLocale] = useState(initialLocale);
  const value = useMemo(() => ({
    locale,
    copy: copyFor(locale),
    setLocale: (next: UiLocale) => {
      if (!isUiLocale(next)) return;
      document.cookie = `${LOCALE_COOKIE}=${next}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
      setCurrentLocale(next);
    },
  }), [locale]);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return (
    <LocaleContext.Provider value={value}>
      <NextIntlClientProvider locale={locale} messages={messagesFor(locale)} timeZone="America/Bogota">
        {children}
      </NextIntlClientProvider>
    </LocaleContext.Provider>
  );
}

export const useUiLocale = () => useContext(LocaleContext);
export function useCopy(): Copy {
  const { copy } = useUiLocale();
  const current = useRef(copy);
  current.current = copy;
  // Existing callbacks remain stable and read the current locale on invocation.
  // A locale change cannot restart a data-loading effect or reset a dirty form.
  return useCallback((source, values) => current.current(source, values), []);
}

export function CopyText({ text }: {text: string}) {
  return <>{useCopy()(text)}</>;
}
