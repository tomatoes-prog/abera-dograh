export const UI_LOCALES = ["es-419", "en"] as const;
export type UiLocale = (typeof UI_LOCALES)[number];
export const LOCALE_COOKIE = "abera-ui-locale";
export const DEFAULT_UI_LOCALE: UiLocale = "es-419";

export function isUiLocale(value: unknown): value is UiLocale {
  return UI_LOCALES.some(locale => locale === value);
}

// Only approved locales reach Intl or the catalog loader. The deployment default
// is a runtime variable so both languages use exactly the same Docker image.
export function resolveUiLocale(cookie: unknown, deploymentDefault: unknown): UiLocale {
  return isUiLocale(cookie) ? cookie : isUiLocale(deploymentDefault) ? deploymentDefault : DEFAULT_UI_LOCALE;
}
