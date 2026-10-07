import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import APIKeysPage from "@/app/api-keys/page";
import ExternalProcessingNotice from "@/app/files/ExternalProcessingNotice";
import { LocaleProvider } from "@/i18n/LocaleProvider";

import { AIModelConfigurationV2Editor, type ModelConfigurationDefaultsV2 } from "./AIModelConfigurationV2Editor";

const { apiKeys, serviceKeys } = vi.hoisted(() => ({
    apiKeys: vi.fn().mockResolvedValue({ data: [] }),
    serviceKeys: vi.fn().mockResolvedValue({ data: [] }),
}));
vi.mock("@/client/sdk.gen", () => ({
    getApiKeysApiV1UserApiKeysGet: apiKeys,
    getServiceKeysApiV1UserServiceKeysGet: serviceKeys,
    archiveApiKeyApiV1UserApiKeysApiKeyIdDelete: vi.fn(),
    archiveServiceKeyApiV1UserServiceKeysServiceKeyIdDelete: vi.fn(),
    createApiKeyApiV1UserApiKeysPost: vi.fn(),
    createServiceKeyApiV1UserServiceKeysPost: vi.fn(),
    reactivateApiKeyApiV1UserApiKeysApiKeyIdReactivatePut: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({
    user: { id: "local-user" }, loading: false,
    getAccessToken: async () => "test-only-token", redirectToLogin: vi.fn(),
}) }));
vi.mock("@/context/AppConfigContext", () => ({ useAppConfig: () => ({
    config: { deploymentMode: "oss", dograhMpsEnabled: false }, loading: false,
}) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "America/Bogota" }));
vi.mock("@/components/VoiceSelectorModal", () => ({ VoiceSelectorModal: () => null }));
vi.mock("@/components/ServiceConfigurationForm", () => ({ ServiceConfigurationForm: () => null }));

const defaults: ModelConfigurationDefaultsV2 = {
    dograh: { enabled: false, voices: [], speeds: [], languages: [], defaults: { voice: "alloy", language: "es", speed: 1 } },
    byok: {
        pipeline: { llm: {}, tts: {}, stt: {}, embeddings: {}, default_providers: {} },
        realtime: { realtime: {}, llm: {}, embeddings: {}, default_providers: {} },
    },
};

beforeEach(() => vi.clearAllMocks());

it("offers own providers and explains a legacy configuration without saving over it", () => {
    const save = vi.fn();
    render(<LocaleProvider initialLocale="es-419"><AIModelConfigurationV2Editor
        defaults={defaults} configuration={{ mode: "dograh" }} onSave={save}
    /></LocaleProvider>);
    expect(screen.queryByRole("tab", { name: "Dograh" })).toBeNull();
    expect(screen.getByText(/Tus agentes y archivos se conservan/)).toBeTruthy();
    expect(save).not.toHaveBeenCalled();
});

it("explains document processing and configured providers in Spanish", () => {
    render(<LocaleProvider initialLocale="es-419"><ExternalProcessingNotice /></LocaleProvider>);
    expect(screen.getByText("Tu base de conocimiento")).toBeTruthy();
    expect(screen.getByText(/Los archivos se leen en tu instancia/)).toBeTruthy();
    expect(screen.queryByText(/Model Proxy Service/)).toBeNull();
});

it("does not show a migration notice for a new account", () => {
    render(<LocaleProvider initialLocale="es-419"><AIModelConfigurationV2Editor
        defaults={defaults} onSave={vi.fn()}
    /></LocaleProvider>);
    expect(screen.queryByText(/Esta cuenta usaba/)).toBeNull();
    expect(screen.queryByRole("tab", { name: "Dograh" })).toBeNull();
});

it("keeps local API keys while skipping vendor key requests", async () => {
    render(<LocaleProvider initialLocale="es-419"><APIKeysPage /></LocaleProvider>);
    await waitFor(() => expect(apiKeys).toHaveBeenCalled());
    expect(serviceKeys).not.toHaveBeenCalled();
    expect(screen.queryByText("Dograh Service Keys")).toBeNull();
});
