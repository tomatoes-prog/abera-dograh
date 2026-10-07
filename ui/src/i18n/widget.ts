import type { WidgetTexts } from "@/client/types.gen";

import type { Copy } from "./catalog";

// New tokens receive explicit overrides through the existing settings contract.
// Existing tokens retain their stored/default texts until the owner edits them.
export function newWidgetTextOverrides(defaults: WidgetTexts | null, copy: Copy): Partial<WidgetTexts> {
  return defaults ? Object.fromEntries(Object.entries(defaults).map(([key, text]) => [key, copy(text)])) : {};
}
