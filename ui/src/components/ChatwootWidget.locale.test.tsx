import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";
import { LocaleSwitcher } from "@/i18n/LocaleSwitcher";

vi.mock("next/navigation", () => ({ usePathname: () => "/auth/login" }));

afterEach(() => {
    document.querySelector('script[src="https://support.example.com/packs/js/sdk.js"]')?.remove();
    delete window.chatwootSettings;
    delete window.$chatwoot;
    delete window.chatwootSDK;
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
});

it("changes the support language without recreating the SDK or an active conversation", async () => {
    const fetchConfig = vi.fn().mockResolvedValue({ ok: true, json: async () => ({
        enabled: true, baseUrl: "https://support.example.com", websiteToken: "public-test-widget",
    }) });
    vi.stubGlobal("fetch", fetchConfig);
    const { default: ChatwootWidget } = await import("./ChatwootWidget");
    const setLocale = vi.fn();
    const run = vi.fn();
    window.$chatwoot = { setLocale };
    window.chatwootSDK = { run };

    render(<LocaleProvider initialLocale="es-419"><LocaleSwitcher /><ChatwootWidget /></LocaleProvider>);
    await waitFor(() => expect(document.querySelector('script[src="https://support.example.com/packs/js/sdk.js"]')).not.toBeNull());
    const script = document.querySelector<HTMLScriptElement>('script[src="https://support.example.com/packs/js/sdk.js"]');
    fireEvent.load(script!);
    expect(window.chatwootSettings?.locale).toBe("es");
    expect(window.chatwootSettings?.launcherTitle).toBe("Habla con nosotros");
    expect(run).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en" } });
    expect(setLocale).toHaveBeenLastCalledWith("en");
    expect(window.chatwootSettings?.locale).toBe("en");
    expect(run).toHaveBeenCalledOnce();
    expect(document.querySelectorAll('script[src="https://support.example.com/packs/js/sdk.js"]')).toHaveLength(1);
    expect(fetchConfig).toHaveBeenCalledOnce();
});

it("loads no external support script when the server leaves integration disabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_CHATWOOT_URL", "https://old-support.example.com");
    vi.stubEnv("NEXT_PUBLIC_CHATWOOT_TOKEN", "legacy-widget");
    const fetchConfig = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: false }) });
    vi.stubGlobal("fetch", fetchConfig);
    const { default: ChatwootWidget } = await import("./ChatwootWidget");
    const run = vi.fn();
    window.chatwootSDK = { run };

    render(<LocaleProvider initialLocale="es-419"><ChatwootWidget /></LocaleProvider>);
    await waitFor(() => expect(fetchConfig).toHaveBeenCalledWith("/api/config/chatwoot", { cache: "no-store" }));
    expect(window.chatwootSettings).toBeUndefined();
    expect(document.querySelector('script[src*="/packs/js/sdk.js"]')).toBeNull();
    expect(run).not.toHaveBeenCalled();
});
