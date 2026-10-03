import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { messagesFor } from "./catalog";
import { LOCALE_COOKIE, resolveUiLocale } from "./config";

export default getRequestConfig(async () => {
  const locale = resolveUiLocale((await cookies()).get(LOCALE_COOKIE)?.value, process.env.UI_DEFAULT_LOCALE);
  return { locale, messages: messagesFor(locale), timeZone: "America/Bogota" };
});
