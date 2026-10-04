import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WidgetTexts } from "@/client/types.gen";
import { copyFor } from "@/i18n/catalog";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { LocaleSwitcher } from "@/i18n/LocaleSwitcher";
import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { EmbedDialog } from "./EmbedDialog";

const { getToken, saveToken, disableToken } = vi.hoisted(() => ({
    getToken: vi.fn(),
    saveToken: vi.fn(),
    disableToken: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
    getEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenGet: getToken,
    createOrUpdateEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenPost: saveToken,
    deactivateEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenDelete: disableToken,
}));

const copy = copyFor("es-419");
const defaults = {
    endChatText: "End chat",
    voiceConnectedTitle: "Connected",
} as WidgetTexts;
const token = {
    id: 7, token: "test-widget", is_active: true, settings: null,
    allowed_domains: ["example.com"], usage_count: 0,
    embed_script: "<script>existing-widget</script>",
};

function showDialog() {
    render(
        <LocaleProvider initialLocale="es-419">
            <LocaleSwitcher />
            <EmbedDialog
                open
                onOpenChange={vi.fn()}
                workflowId={5}
                workflowName="Save {{phone_number}}"
                workflowConfigurations={resolveWorkflowConfigurations()}
                textChatInactivityTimeoutConstraints={null}
                widgetTextDefaults={defaults}
                onSaveWorkflowConfigurations={vi.fn()}
            />
        </LocaleProvider>,
    );
}

describe("widget text ownership across UI locales", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        saveToken.mockResolvedValue({ data: token });
    });

    it("saves translated defaults for a new widget through the existing API contract", async () => {
        getToken.mockResolvedValue({ data: null });
        showDialog();
        const toggle = await screen.findByRole("switch");
        fireEvent.click(toggle);
        fireEvent.click(screen.getByRole("button", { name: copy("Save Configurations") }));
        await waitFor(() => expect(saveToken).toHaveBeenCalledOnce());
        expect(saveToken.mock.calls[0][0].body.settings).toMatchObject({
            endChatText: "Finalizar chat",
            voiceConnectedTitle: "Conectado",
            buttonText: copy("Talk to Agent"),
        });
        expect(defaults.endChatText).toBe("End chat");
    });

    it("preserves published customer text even when it resembles a catalog key", async () => {
        getToken.mockResolvedValue({ data: {
            ...token,
            settings: { buttonText: "Save", voiceConnectedTitle: "Connected {{customer}}" },
        } });
        showDialog();
        await screen.findByRole("button", { name: copy("Save Configurations") });
        fireEvent.change(screen.getByLabelText(copy("Interface language")), {
            target: { value: "en" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save Configurations" }));
        await waitFor(() => expect(saveToken).toHaveBeenCalledOnce());
        expect(saveToken.mock.calls[0][0].body.settings).toMatchObject({
            buttonText: "Save",
            voiceConnectedTitle: "Connected {{customer}}",
        });
        expect(getToken).toHaveBeenCalledOnce();
    });

    it("retains English defaults for an old token without customized settings", async () => {
        getToken.mockResolvedValue({ data: token });
        showDialog();
        fireEvent.click(await screen.findByRole("button", { name: copy("Save Configurations") }));
        await waitFor(() => expect(saveToken).toHaveBeenCalledOnce());
        expect(saveToken.mock.calls[0][0].body.settings.buttonText).toBe("Talk to Agent");
        expect(saveToken.mock.calls[0][0].body.settings).not.toHaveProperty("endChatText");
    });

    it("does not overwrite a published widget when the SDK resolves an HTTP error", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        getToken.mockResolvedValue({ error: { detail: "Unavailable" } });
        showDialog();
        expect((await screen.findByRole("alert")).textContent).toContain(copy("Failed to load widget configuration"));
        expect(screen.queryByRole("button", { name: copy("Save Configurations") })).toBeNull();
        expect(saveToken).not.toHaveBeenCalled();
        vi.restoreAllMocks();
    });
});
