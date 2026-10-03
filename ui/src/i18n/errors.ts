import { detailFromError } from "@/lib/apiError";

import type { Copy } from "./catalog";
import sourceIds from "./messages/sources.json";

export function apiErrorMessage(error: unknown, copy: Copy, fallback = "Something went wrong. Please try again."): string {
  const detail = detailFromError(error, fallback);
  if (Object.prototype.hasOwnProperty.call(sourceIds, detail)) return copy(detail);
  return copy(fallback);
}
