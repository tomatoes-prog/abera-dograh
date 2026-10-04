"use client";

// Shared reassurance line shown beneath every lead-form submit. A small,
// consistent trust signal — keeps the promise identical across all forms.


import { useCopy } from "@/i18n/LocaleProvider";
export function FormTrustLine() {
    const copy = useCopy();
  return (
    <p className="text-center text-xs text-muted-foreground">{copy("Average response: under 10 minutes during business hours.")}</p>
  );
}
