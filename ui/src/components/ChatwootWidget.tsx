"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { useCopy, useUiLocale } from "@/i18n/LocaleProvider";

declare global {
  interface Window {
    chatwootSDK?: {
      run: (config: {
        websiteToken: string;
        baseUrl: string;
      }) => void;
    };
    chatwootSettings?: {
      position?: "left" | "right";
      type?: "standard" | "expanded_bubble";
      launcherTitle?: string;
      locale?: string;
    };
    $chatwoot?: {
      toggleBubbleVisibility?: (visibility: "hide" | "show") => void;
      toggle?: (state?: "open" | "close") => void;
      setLocale?: (locale: string) => void;
    };
  }
}

// Hide the support bubble only on the workflow builder (/workflow/<id> and its
// sub-routes), where the in-app chat tester occupies the same bottom-right
// corner. It stays visible everywhere else, including the /workflow list and
// /workflow/create.
const isBuilderPath = (pathname: string) =>
  /^\/workflow\/(?!create(?:$|\/))[^/]+(?:\/.*)?$/.test(pathname);

export default function ChatwootWidget() {
  const pathname = usePathname();
  const copy = useCopy();
  const { locale } = useUiLocale();
  const chatLocale = locale === "es-419" ? "es" : "en";
  const widgetLanguage = useRef({ locale: chatLocale, title: copy("Chat with us") });
  widgetLanguage.current = { locale: chatLocale, title: copy("Chat with us") };

  // The support widget is an optional external script. Load it only when an
  // operator explicitly configures it on the server.
  useEffect(() => {
    let cancelled = false;
    const loadChatwoot = async () => {
      try {
        const response = await fetch("/api/config/chatwoot", { cache: "no-store" });
        if (!response.ok) return;
        const config = await response.json();
        if (
          cancelled ||
          config.enabled !== true ||
          !config.baseUrl ||
          !config.websiteToken
        ) {
          return;
        }

        const start = () => {
          if (cancelled || window.chatwootSettings || !window.chatwootSDK) return;
          window.chatwootSettings = {
            position: "right",
            type: "standard",
            launcherTitle: widgetLanguage.current.title,
            locale: widgetLanguage.current.locale,
          };
          window.chatwootSDK.run({
            websiteToken: config.websiteToken,
            baseUrl: config.baseUrl,
          });
        };

        const scriptUrl = `${config.baseUrl}/packs/js/sdk.js`;
        const existingScript = document.querySelector(`script[src="${scriptUrl}"]`);
        if (existingScript) {
          existingScript.addEventListener("load", start, { once: true });
          start();
          return;
        }

        const script = document.createElement("script");
        script.src = scriptUrl;
        script.async = true;
        script.defer = true;
        script.onload = start;
        document.body.appendChild(script);
      } catch {
        // Support integration is optional and must never block the application.
      }
    };

    void loadChatwoot();
    return () => {
      cancelled = true;
    };
  }, []);

  // Chatwoot's documented locale API updates an existing widget without
  // recreating the SDK or losing an active support conversation.
  useEffect(() => {
    const applyLocale = () => window.$chatwoot?.setLocale?.(chatLocale);
    if (window.chatwootSettings) window.chatwootSettings.locale = chatLocale;
    applyLocale();
    window.addEventListener("chatwoot:ready", applyLocale, { once: true });
    return () => window.removeEventListener("chatwoot:ready", applyLocale);
  }, [chatLocale]);

  // Show/hide the bubble per route using Chatwoot's native API. We never tear
  // down and recreate the SDK — doing so left the bubble permanently hidden
  // once a user had visited the builder.
  useEffect(() => {
    const applyVisibility = () => {
      if (!window.$chatwoot) return;
      if (isBuilderPath(pathname)) {
        window.$chatwoot.toggle?.("close");
        window.$chatwoot.toggleBubbleVisibility?.("hide");
      } else {
        window.$chatwoot.toggleBubbleVisibility?.("show");
      }
    };

    // Apply immediately only once the bubble holder is actually in the DOM.
    // `window.$chatwoot` exists synchronously after run(), but `.woot--bubble-holder`
    // is appended later when the widget iframe loads, and toggleBubbleVisibility()
    // dereferences it with no null check. When it's absent, fall through to
    // `chatwoot:ready`, which the SDK fires once the holder exists.
    if (window.$chatwoot && document.querySelector(".woot--bubble-holder")) {
      applyVisibility();
      return;
    }

    window.addEventListener("chatwoot:ready", applyVisibility, { once: true });
    return () => window.removeEventListener("chatwoot:ready", applyVisibility);
  }, [pathname]);

  return null;
}
