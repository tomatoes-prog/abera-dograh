// Single submission seam for all lead forms.
// Sends minimal optional analytics metadata and POSTs form contents only to the
// separately configured user_onboarding service (best-effort).
// No auth token: identity is the email in the payload.

import { PostHogEvent } from "@/constants/posthog-events";
import { captureAnalyticsEvent } from "@/lib/analytics";
import { trackMetaLead } from "@/lib/metaPixel";

import { detectCountry, detectTimezone } from "./detectCountry";
import type { LeadKind, LeadOrigin, LeadSource } from "./leadFieldOptions";
import { type LeadResult, postLeadToService } from "./onboardingServiceClient";

const SUBMIT_EVENT: Record<LeadKind, string> = {
  hire_expert: PostHogEvent.HIRE_EXPERT_SUBMITTED,
  enterprise: PostHogEvent.ENTERPRISE_LEAD_SUBMITTED,
};

export interface SubmitLeadArgs {
  kind: LeadKind;
  source: LeadSource;
  // Deployment provenance (analytics only): "cloud_app" | "oss_app".
  origin: LeadOrigin;
  // Field values, already validated by the caller. Includes the contact email.
  payload: Record<string, unknown>;
}

export async function submitLead({ kind, source, origin, payload }: SubmitLeadArgs): Promise<LeadResult | null> {
  // Country and timezone are attached to the explicitly configured form service
  // payload only; they are not included in analytics.
  const body = { source, origin, country: detectCountry(), timezone: detectTimezone(), ...payload };
  // Analytics receives only coarse form metadata, never contact details,
  // answers, country, or timezone.
  captureAnalyticsEvent(SUBMIT_EVENT[kind], { kind, source, origin });
  trackMetaLead({ content_name: kind, source });
  // Persist to the separate user_onboarding service (best-effort, public); return its verdict.
  return postLeadToService(kind, body);
}
