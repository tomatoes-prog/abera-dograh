"use client";

import { Languages } from "lucide-react";

import { isUiLocale } from "./config";
import { useUiLocale } from "./LocaleProvider";

export function LocaleSwitcher({ compact = false }: {compact?: boolean}) {
  const { locale, copy, setLocale } = useUiLocale();
  return <label className="inline-flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-xs text-muted-foreground">
    <Languages className="h-4 w-4 shrink-0" aria-hidden="true" />
    <span className="sr-only">{copy("Interface language")}</span>
    <select aria-label={copy("Interface language")} value={locale}
      className={`min-w-0 cursor-pointer rounded-md border border-border bg-background py-1 ${compact ? "w-12" : "max-w-40 px-2"}`}
      onChange={event => {if (isUiLocale(event.target.value)) setLocale(event.target.value);}}>
      <option value="es-419">{compact ? "ES" : "Español (Latinoamérica)"}</option>
      <option value="en">{compact ? "EN" : "English"}</option>
    </select>
  </label>;
}
