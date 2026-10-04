// This file configures the initialization of Sentry on the client.
// The added config here will be used whenever a users loads a page in their browser.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";
import posthog from "posthog-js";

// Drop errors originating from browser extensions (MetaMask's inpage.js,
// injected widgets, etc.) by matching their URL scheme.
const sharedSentryOptions = {
  debug: false,
  denyUrls: [
    /^chrome-extension:\/\//i,
    /^moz-extension:\/\//i,
    /^safari-extension:\/\//i,
    /^safari-web-extension:\/\//i,
  ],
};

// Telemetry uses server-side runtime config only. Public build-time keys must not
// bypass ENABLE_TELEMETRY, and no tracking SDK initializes when it is disabled.
const initializeSentry = async () => {
  try {
    const response = await fetch('/api/config/sentry', { cache: 'no-store' });
    if (!response.ok) return;
    const config = await response.json();
    if (config.enabled === true && config.dsn) {
      Sentry.init({
        dsn: config.dsn,
        sendDefaultPii: false,
        ...sharedSentryOptions,
      });
    }
  } catch {
    // Telemetry configuration is optional. A failure must not affect the app.
  }
};

const initializePostHog = async () => {
  try {
    const response = await fetch('/api/config/posthog', { cache: 'no-store' });
    if (!response.ok) return;
    const config = await response.json();
    if (config.enabled === true && config.key) {
      posthog.init(config.key, {
        api_host: config.host,
        ui_host: config.uiHost,
        autocapture: false,
        capture_pageview: false,
        capture_pageleave: false,
        capture_exceptions: false,
        cross_subdomain_cookie: false,
        persistence: 'memory',
      });
    }
  } catch {
    // Telemetry configuration is optional. A failure must not affect the app.
  }
};

void initializeSentry();
void initializePostHog();


export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
