import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import APIKeysPage from "@/app/api-keys/page";
import ExternalProcessingNotice from "@/app/files/ExternalProcessingNotice";
import { LocaleProvider } from "@/i18n/LocaleProvider";

import { emptyConfiguration } from "./model-connections/configuration";
import { ConfigurationFields } from "./model-connections/ConfigurationFields";
import type { ModelConnectionCatalog } from "./model-connections/types";

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

const catalog: ModelConnectionCatalog = {services: {llm: {}, stt: {}, tts: {}, realtime: {}, embeddings: {}}};

beforeEach(() => vi.clearAllMocks());

it("keeps managed services unavailable without replacing the saved configuration", () => {
    const save = vi.fn();
    render(<LocaleProvider initialLocale="es-419"><ConfigurationFields
        catalog={catalog} connections={[{uuid: "legacy", name: "Legacy", provider: "dograh", revision: 1, is_active: true, configured_credentials: [], connection_settings: {}}]}
        configuration={{version: 3, mode: "pipeline", llm: {provider_connection_uuid: "legacy", settings: {}}, stt: {provider_connection_uuid: "legacy", settings: {}}, tts: {provider_connection_uuid: "legacy", settings: {}}}} onChange={save}
    /></LocaleProvider>);
    expect(screen.queryByRole("radio", {name: "Dograh"})).toBeNull();
    expect(screen.getByRole("alert").textContent).toMatch(/tus agentes y archivos se conservan/i);
    expect(save).not.toHaveBeenCalled();
});

it("explains document processing and configured providers in Spanish", () => {
    render(<LocaleProvider initialLocale="es-419"><ExternalProcessingNotice /></LocaleProvider>);
    expect(screen.getByText("Tu base de conocimiento")).toBeTruthy();
    expect(screen.getByText(/Los archivos se leen en tu instancia/)).toBeTruthy();
    expect(screen.queryByText(/Model Proxy Service/)).toBeNull();
});

it("does not show a migration notice for a new account", () => {
    render(<LocaleProvider initialLocale="es-419"><ConfigurationFields
        catalog={catalog} connections={[]} configuration={emptyConfiguration(catalog, [], "cascade")} onChange={vi.fn()}
    /></LocaleProvider>);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("radio", {name: "Dograh"})).toBeNull();
});

it("keeps local API keys while skipping vendor key requests", async () => {
    render(<LocaleProvider initialLocale="es-419"><APIKeysPage /></LocaleProvider>);
    await waitFor(() => expect(apiKeys).toHaveBeenCalled());
    expect(serviceKeys).not.toHaveBeenCalled();
    expect(screen.queryByText("Dograh Service Keys")).toBeNull();
});
