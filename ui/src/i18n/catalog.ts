import { createTranslator, type TranslationValues } from "next-intl";

import type { UiLocale } from "./config";
import english from "./messages/en.json";
import spanish from "./messages/es-419.json";
import sourceIds from "./messages/sources.json";

export type Copy = (source: string, values?: TranslationValues) => string;
const ids: Record<string, string> = sourceIds;
export const messagesFor = (locale: UiLocale) => locale === "es-419" ? spanish : english;

export function copyFor(locale: UiLocale): Copy {
  const translate = createTranslator({ locale, messages: messagesFor(locale), namespace: "copy" });
  return (source, values) => {
    const id = Object.prototype.hasOwnProperty.call(ids, source) ? ids[source] : undefined;
    // This also lets new upstream metadata render until its catalog entry is reviewed.
    // It must only be used for application copy, never arbitrary customer content.
    return id ? translate(id as keyof typeof english.copy, values) : source;
  };
}
