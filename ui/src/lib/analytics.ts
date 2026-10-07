import posthog from "posthog-js";

/** Send an event only after PostHog was explicitly enabled by runtime config. */
export function captureAnalyticsEvent(
  event: string,
  properties?: Record<string, unknown>,
): void {
  if (!posthog.__loaded) return;
  posthog.capture(event, properties);
}
