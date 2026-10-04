import posthog from "posthog-js";
import { afterEach, describe, expect, it, vi } from "vitest";

import { captureAnalyticsEvent } from "./analytics";

vi.mock("posthog-js", () => ({
  default: { __loaded: false, capture: vi.fn() },
}));

describe("captureAnalyticsEvent", () => {
  afterEach(() => {
    Object.defineProperty(posthog, "__loaded", { value: false, configurable: true });
    vi.mocked(posthog.capture).mockClear();
  });

  it("drops events until runtime telemetry configuration initializes PostHog", () => {
    captureAnalyticsEvent("workflow_opened", { workflow_id: 1 });

    expect(posthog.capture).not.toHaveBeenCalled();
  });

  it("sends events after PostHog has been initialized", () => {
    Object.defineProperty(posthog, "__loaded", { value: true, configurable: true });

    captureAnalyticsEvent("workflow_opened", { workflow_id: 1 });

    expect(posthog.capture).toHaveBeenCalledWith("workflow_opened", {
      workflow_id: 1,
    });
  });
});
