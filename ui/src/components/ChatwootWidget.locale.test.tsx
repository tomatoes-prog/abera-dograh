import { fireEvent, render, screen } from "@testing-library/react";
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
});

it("changes the support language without recreating the SDK or an active conversation", async () => {
    vi.stubEnv("NEXT_PUBLIC_CHATWOOT_URL", "https://support.example.com");
    vi.stubEnv("NEXT_PUBLIC_CHATWOOT_TOKEN", "public-test-widget");
    const { default: ChatwootWidget } = await import("./ChatwootWidget");
    const setLocale = vi.fn();
    const run = vi.fn();
    window.$chatwoot = { setLocale };
    window.chatwootSDK = { run };

    render(<LocaleProvider initialLocale="es-419"><LocaleSwitcher /><ChatwootWidget /></LocaleProvider>);
    const script = document.querySelector<HTMLScriptElement>('script[src="https://support.example.com/packs/js/sdk.js"]');
    expect(window.chatwootSettings?.locale).toBe("es");
    expect(window.chatwootSettings?.launcherTitle).toBe("Habla con nosotros");
    fireEvent.load(script!);
    expect(run).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en" } });
    expect(setLocale).toHaveBeenLastCalledWith("en");
    expect(window.chatwootSettings?.locale).toBe("en");
    expect(run).toHaveBeenCalledOnce();
    expect(document.querySelectorAll('script[src="https://support.example.com/packs/js/sdk.js"]')).toHaveLength(1);
});
