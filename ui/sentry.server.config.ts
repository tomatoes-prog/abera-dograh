// This file configures the initialization of Sentry on the server.
// The config you add here will be used whenever the server handles a request.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";

// No Sentry traffic unless the operator explicitly enables telemetry and sets a DSN.
const enableSentry = process.env.ENABLE_TELEMETRY === "true";

if (enableSentry && process.env.SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.SENTRY_DSN,

    // Setting this option to true will print useful information to the console while you're setting up Sentry.
    debug: false,
    enabled: true,
    sendDefaultPii: false,
  });
  console.log('Sentry initialized for server-side error tracking');
}
