import { enUS, es } from "date-fns/locale";

import type { UiLocale } from "./config";
export const dateFnsLocale = (locale: UiLocale) => locale === "es-419" ? es : enUS;

export function languageDisplayName(code: string, locale: UiLocale, fallback?: string): string {
  if (code === "multi") {
    return locale === "es-419" ? "Varios idiomas (detección automática)" : "Multilingual (Auto-detect)";
  }
  try {
    return new Intl.DisplayNames([locale], { type: "language" }).of(code) || fallback || code;
  } catch {
    return fallback || code;
  }
}
