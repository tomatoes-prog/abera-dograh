import { enUS, es } from "date-fns/locale";

import { ACCENT_DISPLAY_NAMES } from "@/constants/accents";

import type { Copy } from "./catalog";
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

export function voiceGenderLabel(code: string | null | undefined, copy: Copy): string {
  const labels: Record<string, string> = {female: "Female", male: "Male", neutral: "Neutral", nonbinary: "Non-binary"};
  return code ? labels[code.toLowerCase()] ? copy(labels[code.toLowerCase()]) : code : "";
}

export function voiceAccentLabel(code: string | null | undefined, copy: Copy): string {
  return code ? ACCENT_DISPLAY_NAMES[code.toLowerCase()] ? copy(ACCENT_DISPLAY_NAMES[code.toLowerCase()]) : code : "";
}
