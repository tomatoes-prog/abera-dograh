// Submission seam for the post-signup onboarding form.
// Sends minimal optional analytics metadata and POSTs the answers only to the
// separately configured user_onboarding service (best-effort). The "show once per
// user" flag is stamped on the server-backed onboarding state by the caller.
//
// No auth token. The logged-in user's email is passed in from the modal (available in
// the frontend session for both cloud and OSS) and sent in the body — there is no
// visible email field. `country` is detected silently and sent too. Onboarding is now
// COMPULSORY (no skip).

import { PostHogEvent } from "@/constants/posthog-events";
import { captureAnalyticsEvent } from "@/lib/analytics";
import { trackMetaLead } from "@/lib/metaPixel";

import { detectCountry } from "./detectCountry";
import type { LeadOrigin } from "./leadFieldOptions";
import { postOnboardingToService } from "./onboardingServiceClient";

export interface OnboardingAnswers {
  persona?: string;
  // Only present when persona unlocks the on-prem question.
  onPremNeed?: string;
  // Are you migrating from another provider? ("no" | a provider | "other").
  migratingFrom?: string;
  // Free-text provider name when migratingFrom === "other".
  migratingOtherProvider?: string;
  // Free-text "why are you switching?" (shown when migrating).
  switchReason?: string;
  // How did you hear about us?
  howHeard?: string;
  // Expected monthly call volume (0-5k | 5k-100k | 100k+ | exploring).
  volume?: string;
}

export async function submitOnboarding(
  answers: OnboardingAnswers,
  origin: LeadOrigin,
  email?: string,
): Promise<void> {
  captureAnalyticsEvent(PostHogEvent.ONBOARDING_SUBMITTED, { origin });
  trackMetaLead({ content_name: "onboarding", origin });
  await postOnboardingToService({
    source: "onboarding",
    origin,
    country: detectCountry(),
    ...(email ? { email } : {}),
    ...answers,
    skipped: false, // onboarding is compulsory now — kept for stored-shape continuity
  });
}
