/**
 * Meta (Facebook) Pixel — thin, guarded tracking seam.
 *
 * These helpers run only when the root layout loads Meta Pixel under the explicit
 * telemetry opt-in. Otherwise `window.fbq` is absent and each call is a no-op.
 *
 * Every helper is a no-op unless the Pixel is actually loaded (i.e. `window.fbq`
 * exists). A configured pixel ID alone does not activate it: ENABLE_TELEMETRY
 * must also be true (see app/layout.tsx).
 */

declare global {
  interface Window {
    fbq?: (...args: unknown[]) => void;
  }
}

type MetaEventParams = Record<string, unknown>;

/** Fire a Meta standard event, guarded on the Pixel being loaded. */
function metaTrack(event: string, params?: MetaEventParams): void {
  if (typeof window === "undefined" || typeof window.fbq !== "function") return;
  if (params) {
    window.fbq("track", event, params);
  } else {
    window.fbq("track", event);
  }
}

export function trackMetaPageView(): void {
  metaTrack("PageView");
}

export function trackMetaCompleteRegistration(params?: MetaEventParams): void {
  metaTrack("CompleteRegistration", params);
}

export function trackMetaLead(params?: MetaEventParams): void {
  metaTrack("Lead", params);
}

export function trackMetaInitiateCheckout(params?: MetaEventParams): void {
  metaTrack("InitiateCheckout", params);
}
