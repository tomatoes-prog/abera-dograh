"use client";

import { Check, ChevronDown, Copy, ExternalLink, Loader2, MessageCircle, Mic, Plus, Rocket, Send, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
    createOrUpdateEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenPost,
    deactivateEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenDelete,
    getEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenGet,
} from "@/client/sdk.gen";
import type { TextChatInactivityTimeoutConstraints, WidgetTexts } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { WIDGET_CONTEXT_DOC_URL, WIDGET_MODE_DOCUMENTATION_URLS } from "@/constants/documentation";
import { HEADLESS_CHAT_EXAMPLE } from "@/constants/embedExamples";
import { useCopy } from "@/i18n/LocaleProvider";
import { newWidgetTextOverrides } from "@/i18n/widget";
import { detailFromError } from "@/lib/apiError";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";


interface EmbedDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    workflowId: number;
    workflowName: string;
    workflowConfigurations: WorkflowConfigurations;
    textChatInactivityTimeoutConstraints: TextChatInactivityTimeoutConstraints | null;
    widgetTextDefaults: WidgetTexts | null;
    onSaveWorkflowConfigurations: (
        configurations: WorkflowConfigurations,
        workflowName: string,
    ) => Promise<void>;
}

type WidgetType = "voice" | "chat";

// Per-type defaults, swapped on toggle only when the user hasn't customized
// the text (i.e. it still equals the other type's default).
const WIDGET_TYPE_DEFAULTS: Record<WidgetType, { buttonText: string; callToActionText: string }> = {
    voice: {
        buttonText: "Talk to Agent",
        callToActionText: "Click to start voice conversation",
    },
    chat: {
        buttonText: "Chat with Agent",
        callToActionText: "Click to start chatting",
    },
};

// Visitor-facing copy the agent owner can translate. The default strings live
// only in api/schemas/widget_texts.py — they reach this dialog as placeholders
// via the generated client, and reach the widget already resolved. Everything
// below is presentation: which key goes in which group, and what to call it.
type WidgetTextKey = keyof WidgetTexts;

interface WidgetTextField {
    key: WidgetTextKey;
    label: string;
    hint?: string;
}

const CHAT_TEXT_FIELDS: WidgetTextField[] = [
    { key: "endChatText", label: "End Chat Button" },
    { key: "endChatConfirmText", label: "End Chat Confirmation" },
    { key: "endChatCancelText", label: "Cancel Button", hint: "shown next to the confirmation" },
    { key: "endingChatText", label: "Ending Chat Status" },
    { key: "conversationEndedText", label: "Conversation Ended Message" },
    { key: "startNewChatText", label: "Start New Chat Button" },
    { key: "chatRetryText", label: "Retry Button" },
    { key: "chatInputPlaceholder", label: "Message Input Placeholder" },
    { key: "sendMessageLabel", label: "Send Button Label", hint: "screen readers only" },
    { key: "closeChatLabel", label: "Close Button Label", hint: "screen readers only" },
];

// Floating voice widgets only ever show the CTA pill, so they get the button
// labels alone; the status headings below are inline-only.
const VOICE_BUTTON_TEXT_FIELDS: WidgetTextField[] = [
    { key: "voiceConnectingText", label: "Connecting" },
    { key: "voiceEndCallText", label: "End Call Button" },
    { key: "voiceRetryText", label: "Retry Button" },
];

const VOICE_STATUS_TEXT_FIELDS: WidgetTextField[] = [
    { key: "voiceReadyTitle", label: "Ready Heading", hint: "paired with Call to Action Text" },
    { key: "voiceConnectingSubtext", label: "Connecting Subtext" },
    { key: "voiceConnectedTitle", label: "Connected Heading" },
    { key: "voiceConnectedSubtext", label: "Connected Subtext" },
    { key: "voiceCallEndedTitle", label: "Call Ended Heading" },
    { key: "voiceCallEndedSubtext", label: "Call Ended Subtext" },
    { key: "voiceConnectionFailedTitle", label: "Connection Failed Heading" },
    { key: "voiceConnectionFailedSubtext", label: "Connection Failed Subtext" },
    { key: "voiceConnectionLostTitle", label: "Connection Lost Heading" },
    { key: "voiceConnectionLostSubtext", label: "Connection Lost Subtext" },
];

const WIDGET_TEXT_KEYS: WidgetTextKey[] = [
    ...CHAT_TEXT_FIELDS,
    ...VOICE_BUTTON_TEXT_FIELDS,
    ...VOICE_STATUS_TEXT_FIELDS,
].map((field) => field.key);

/**
 * Collapsed-by-default panel of text overrides. Kept at module scope so
 * toggling it open doesn't remount the inputs and drop focus.
 */
function WidgetTextSection({
    title,
    description,
    groups,
    values,
    defaults,
    onChange,
}: {
    title: string;
    description: string;
    groups: { heading?: string; fields: WidgetTextField[] }[];
    values: Partial<Record<WidgetTextKey, string>>;
    defaults: WidgetTexts | null;
    onChange: (key: WidgetTextKey, value: string) => void;
}) {
    const copy = useCopy();
    const [open, setOpen] = useState(false);

    return (
        <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border bg-muted/20">
            <CollapsibleTrigger className="flex w-full items-center justify-between gap-4 p-4 text-left">
                <div className="space-y-0.5">
                    <div className="text-sm font-medium">{copy(title)}</div>
                    <p className="text-xs text-muted-foreground">{copy(description)}</p>
                </div>
                <ChevronDown
                    className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
                />
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 border-t p-4">
                {groups.map((group, groupIndex) => (
                    <div key={group.heading ?? groupIndex} className="space-y-3">
                        {group.heading && (
                            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                {copy(group.heading)}
                            </div>
                        )}
                        <div className="grid grid-cols-2 gap-4">
                            {group.fields.map(({ key, label, hint }) => (
                                <div key={key} className="space-y-2">
                                    <Label htmlFor={`widget-text-${key}`} className="text-sm">
                                        {copy(label)}
                                        {hint && (
                                            <span className="ml-1 text-xs font-normal text-muted-foreground">
                                                ({copy(hint)})
                                            </span>
                                        )}
                                    </Label>
                                    <Input
                                        id={`widget-text-${key}`}
                                        // Untouched fields show the backend default, so the
                                        // owner edits real copy rather than a blank box.
                                        value={values[key] ?? defaults?.[key] ?? ""}
                                        onChange={(e) => onChange(key, e.target.value)}
                                        placeholder={defaults?.[key] ?? ""}
                                        maxLength={80}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </CollapsibleContent>
        </Collapsible>
    );
}

const SECONDS_PER_MINUTE = 60;

interface EmbedToken {
    id: number;
    token: string;
    allowed_domains: string[] | null;
    settings: Record<string, unknown> | null;
    is_active: boolean;
    usage_count: number;
    usage_limit: number | null;
    expires_at: string | null;
    created_at: string;
    embed_script: string;
}

export function EmbedDialog({
    open,
    onOpenChange,
    workflowId,
    workflowName,
    workflowConfigurations,
    textChatInactivityTimeoutConstraints,
    widgetTextDefaults,
    onSaveWorkflowConfigurations,
}: EmbedDialogProps) {
    const copy = useCopy();
    const [loading, setLoading] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [embedToken, setEmbedToken] = useState<EmbedToken | null>(null);
    const [copied, setCopied] = useState(false);

    // Form state
    const [isEnabled, setIsEnabled] = useState(false);
    const [domains, setDomains] = useState<string[]>([]);
    const [newDomain, setNewDomain] = useState("");
    const [widgetType, setWidgetType] = useState<WidgetType>("voice");
    const [embedMode, setEmbedMode] = useState<"floating" | "inline" | "headless">("floating");
    const [position, setPosition] = useState("bottom-right");
    const [buttonText, setButtonText] = useState(() => copy("Talk to Agent"));
    const [buttonColor, setButtonColor] = useState("#10b981");
    const [callToActionText, setCallToActionText] = useState(() => copy("Click to start voice conversation"));
    // Sparse: only keys the owner has overridden. Anything absent renders (and
    // saves as) the backend default.
    const [widgetTexts, setWidgetTexts] = useState<Partial<Record<WidgetTextKey, string>>>({});
    const configuredTextChatInactivitySeconds =
        workflowConfigurations.text_chat_inactivity_timeout_seconds
        ?? textChatInactivityTimeoutConstraints?.default_seconds;
    const [textChatInactivityMinutes, setTextChatInactivityMinutes] = useState(() =>
        configuredTextChatInactivitySeconds === undefined
            ? ""
            : String(configuredTextChatInactivitySeconds / SECONDS_PER_MINUTE),
    );

    const parsedTextChatInactivityMinutes = Number(textChatInactivityMinutes);
    const parsedTextChatInactivitySeconds =
        parsedTextChatInactivityMinutes * SECONDS_PER_MINUTE;
    const minimumTextChatInactivitySeconds =
        textChatInactivityTimeoutConstraints?.minimum_seconds;
    const maximumTextChatInactivitySeconds =
        textChatInactivityTimeoutConstraints?.maximum_seconds;
    const minimumTextChatInactivityMinutes = minimumTextChatInactivitySeconds !== undefined
        ? minimumTextChatInactivitySeconds / SECONDS_PER_MINUTE
        : undefined;
    const maximumTextChatInactivityMinutes = maximumTextChatInactivitySeconds !== undefined
        ? maximumTextChatInactivitySeconds / SECONDS_PER_MINUTE
        : undefined;
    const hasTextChatInactivityBounds =
        minimumTextChatInactivitySeconds !== undefined &&
        maximumTextChatInactivitySeconds !== undefined;
    const textChatInactivityIsValid =
        textChatInactivityMinutes.trim() !== "" &&
        Number.isInteger(parsedTextChatInactivityMinutes) &&
        (!hasTextChatInactivityBounds ||
            (parsedTextChatInactivitySeconds >=
                minimumTextChatInactivitySeconds &&
                parsedTextChatInactivitySeconds <=
                    maximumTextChatInactivitySeconds));
    const textChatInactivityValidationMessage = hasTextChatInactivityBounds
        ? copy("Chat inactivity timeout must be a whole number between {value0} and {value1} minutes", { value0: minimumTextChatInactivityMinutes!, value1: maximumTextChatInactivityMinutes! })
        : copy("Chat inactivity timeout must be a whole number of minutes");

    const handleWidgetTextChange = useCallback((key: WidgetTextKey, value: string) => {
        setWidgetTexts((prev) => ({ ...prev, [key]: value }));
    }, []);

    const handleWidgetTypeChange = (type: WidgetType) => {
        if (type === widgetType) return;
        const from = WIDGET_TYPE_DEFAULTS[widgetType];
        const to = WIDGET_TYPE_DEFAULTS[type];
        if (buttonText === from.buttonText || buttonText === copy(from.buttonText)) setButtonText(copy(to.buttonText));
        if (callToActionText === from.callToActionText || callToActionText === copy(from.callToActionText)) setCallToActionText(copy(to.callToActionText));
        setWidgetType(type);
    };

    const loadEmbedToken = useCallback(async () => {
        setLoading(true);
        setLoadError(null);
        try {
            const response = await getEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenGet({
                path: { workflow_id: workflowId },
            });

            if (response.error) throw new Error(copy(detailFromError(response.error, "Failed to load widget configuration")));
            if (!response.data) {
                setEmbedToken(null);
                setIsEnabled(false);
                setDomains([]);
                setWidgetType("voice");
                setButtonText(copy(WIDGET_TYPE_DEFAULTS.voice.buttonText));
                setCallToActionText(copy(WIDGET_TYPE_DEFAULTS.voice.callToActionText));
                setWidgetTexts(newWidgetTextOverrides(widgetTextDefaults, copy));
            }
            if (response.data) {
                setEmbedToken(response.data as EmbedToken);
                setIsEnabled(response.data.is_active);

                // Load settings
                {
                    const settings = (response.data.settings ?? {}) as Record<string, string>;
                    const loadedType: WidgetType = settings.widgetType === "chat" ? "chat" : "voice";
                    setWidgetType(loadedType);
                    setEmbedMode((settings.embedMode as "floating" | "inline" | "headless") || "floating");
                    setPosition(settings.position || "bottom-right");
                    setButtonText(settings.buttonText || WIDGET_TYPE_DEFAULTS[loadedType].buttonText);
                    setButtonColor(settings.buttonColor || "#10b981");
                    setCallToActionText(settings.callToActionText || WIDGET_TYPE_DEFAULTS[loadedType].callToActionText);
                    setWidgetTexts(
                        Object.fromEntries(
                            WIDGET_TEXT_KEYS
                                .filter((key) => settings[key])
                                .map((key) => [key, settings[key]]),
                        ),
                    );
                }

                // Load domains
                if (response.data.allowed_domains) {
                    setDomains(response.data.allowed_domains);
                }
            }
        } catch (error) {
            console.error("Failed to load embed token:", error);
            setLoadError(copy("Failed to load widget configuration"));
        } finally {
            setLoading(false);
        }
    }, [workflowId, widgetTextDefaults, copy]);

    useEffect(() => {
        if (open) {
            loadEmbedToken();
            setTextChatInactivityMinutes(
                configuredTextChatInactivitySeconds === undefined
                    ? ""
                    : String(configuredTextChatInactivitySeconds / SECONDS_PER_MINUTE),
            );
        }
    }, [open, loadEmbedToken, configuredTextChatInactivitySeconds]);

    const handleSave = async () => {
        if (loading || loadError) return;
        if (isEnabled && widgetType === "chat" && !textChatInactivityIsValid) {
            toast.error(textChatInactivityValidationMessage);
            return;
        }

        setSaving(true);
        try {
            if (isEnabled && widgetType === "chat") {
                await onSaveWorkflowConfigurations(
                    {
                        ...workflowConfigurations,
                        text_chat_inactivity_timeout_seconds: parsedTextChatInactivitySeconds,
                    },
                    workflowName,
                );
            }

            if (!isEnabled && embedToken) {
                // Deactivate token
                const response = await deactivateEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenDelete({
                    path: { workflow_id: workflowId },
                });
                if (response.error) {
                    throw new Error(
                        copy(detailFromError(response.error, "Failed to disable embedding")),
                    );
                }
                setEmbedToken(null);
            } else if (isEnabled) {
                // Create or update token
                const response = await createOrUpdateEmbedTokenApiV1WorkflowWorkflowIdEmbedTokenPost({
                    path: { workflow_id: workflowId },
                    body: {
                        allowed_domains: domains.length > 0 ? domains : null,
                        settings: {
                            widgetType,
                            embedMode,
                            position,
                            buttonText,
                            buttonColor,
                            callToActionText,
                            // Overrides only — a key left out resolves to the
                            // backend default, so default copy keeps improving
                            // for tokens that never customized it.
                            ...Object.fromEntries(
                                WIDGET_TEXT_KEYS
                                    .map((key) => [key, (widgetTexts[key] ?? "").trim()])
                                    .filter(([, value]) => value !== ""),
                            ),
                            size: "medium",
                            autoStart: false,
                            containerId: embedMode === "inline" ? "dograh-inline-container" : undefined,
                        },
                        usage_limit: null,
                        expires_in_days: null,
                    },
                });

                if (response.error) {
                    throw new Error(
                        copy(detailFromError(response.error, "Failed to save widget configuration")),
                    );
                }
                if (response.data) {
                    setEmbedToken(response.data as EmbedToken);
                }
            }

            toast.success(
                copy("Widget configuration saved. Publish the agent to apply the changes."),
            );
            // Don't close modal after saving - let user copy the embed code
        } catch (error) {
            console.error("Failed to save embed token:", error);
            toast.error(
                error instanceof Error ? copy(error.message) : copy("Failed to save widget configuration"),
            );
        } finally {
            setSaving(false);
        }
    };

    const copyToClipboard = async (text: string) => {
        try {
            await copyTextToClipboard(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            toast.error(copy("Failed to copy embed code"));
        }
    };

    const addDomain = () => {
        if (newDomain.trim() && !domains.includes(newDomain.trim())) {
            setDomains([...domains, newDomain.trim()]);
            setNewDomain("");
        }
    };

    const removeDomain = (domain: string) => {
        setDomains(domains.filter(d => d !== domain));
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addDomain();
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-4xl w-full max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <div className="flex items-center justify-between">
                        <DialogTitle className="flex items-center gap-2">
                            <Rocket className="h-5 w-5" />{copy("Configure Widget")}</DialogTitle>
                        <a
                            href={WIDGET_MODE_DOCUMENTATION_URLS[embedMode]}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors pr-6"
                        >{copy("Docs")}<ExternalLink className="h-3.5 w-3.5" />
                        </a>
                    </div>
                    <DialogDescription>{copy("Add \"")}{workflowName}{copy("\" to any website with a simple script tag.")}</DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                ) : loadError ? (
                    <div role="alert" className="space-y-3 py-4">
                        <p className="text-sm text-destructive">{loadError}</p>
                        <Button variant="outline" onClick={loadEmbedToken}>{copy("Retry")}</Button>
                    </div>
                ) : (
                    <div className="space-y-6">
                        {/* Enable/Disable Toggle */}
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label htmlFor="embed-enabled">{copy("Enable Embedding")}</Label>
                                <p className="text-sm text-muted-foreground">{copy("Allow this workflow to be embedded on external websites")}</p>
                            </div>
                            <Switch
                                id="embed-enabled"
                                checked={isEnabled}
                                onCheckedChange={setIsEnabled}
                            />
                        </div>

                        {isEnabled && (
                            <>
                                <Separator />

                                {/* Allowed Domains */}
                                <div className="space-y-3">
                                    <Label>{copy("Allowed Domains")}<span className="text-xs text-muted-foreground ml-2">{copy("(leave empty to allow all domains)")}</span>
                                    </Label>

                                    {/* Domain Input */}
                                    <div className="flex gap-2">
                                        <Input
                                            placeholder={copy("example.com or *.example.com")}
                                            value={newDomain}
                                            onChange={(e) => setNewDomain(e.target.value)}
                                            onKeyPress={handleKeyPress}
                                        />
                                        <Button
                                            type="button"
                                            size="icon"
                                            variant="outline"
                                            onClick={addDomain}
                                            disabled={!newDomain.trim()}
                                        >
                                            <Plus className="h-4 w-4" />
                                        </Button>
                                    </div>

                                    {/* Domain List */}
                                    {domains.length > 0 && (
                                        <div className="space-y-2">
                                            {domains.map((domain, index) => (
                                                <div
                                                    key={index}
                                                    className="flex items-center justify-between bg-muted/50 rounded-lg px-3 py-2"
                                                >
                                                    <span className="text-sm font-mono">{domain}</span>
                                                    <Button
                                                        type="button"
                                                        size="icon"
                                                        variant="ghost"
                                                        className="h-6 w-6"
                                                        onClick={() => removeDomain(domain)}
                                                    >
                                                        <Trash2 className="h-3 w-3" />
                                                    </Button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Widget Type Selection */}
                                <div className="space-y-4">
                                    <Label>{copy("Widget Type")}</Label>
                                    <div className="grid grid-cols-2 gap-4">
                                        <button
                                            type="button"
                                            onClick={() => handleWidgetTypeChange("voice")}
                                            className={`p-4 rounded-lg border-2 transition-all ${
                                                widgetType === "voice"
                                                    ? "border-primary bg-primary/5"
                                                    : "border-muted hover:border-muted-foreground/20"
                                            }`}
                                        >
                                            <div className="space-y-2">
                                                <div className="flex items-center justify-center gap-2 font-medium">
                                                    <Mic className="h-4 w-4" />{copy("Voice Agent")}</div>
                                                <div className="text-xs text-muted-foreground">{copy("Visitors talk to your agent by voice")}</div>
                                            </div>
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleWidgetTypeChange("chat")}
                                            className={`p-4 rounded-lg border-2 transition-all ${
                                                widgetType === "chat"
                                                    ? "border-primary bg-primary/5"
                                                    : "border-muted hover:border-muted-foreground/20"
                                            }`}
                                        >
                                            <div className="space-y-2">
                                                <div className="flex items-center justify-center gap-2 font-medium">
                                                    <MessageCircle className="h-4 w-4" />{copy("Chat Agent")}</div>
                                                <div className="text-xs text-muted-foreground">{copy("Visitors type messages to your agent")}</div>
                                            </div>
                                        </button>
                                    </div>
                                </div>

                                {widgetType === "chat" && (
                                    <div className="space-y-2 rounded-lg border bg-muted/20 p-4">
                                        <Label htmlFor="text-chat-inactivity-timeout">{copy("Chat Inactivity Timeout")}</Label>
                                        <div className="flex items-center gap-2">
                                            <Input
                                                id="text-chat-inactivity-timeout"
                                                type="number"
                                                min={minimumTextChatInactivityMinutes}
                                                max={maximumTextChatInactivityMinutes}
                                                step="1"
                                                value={textChatInactivityMinutes}
                                                onChange={(event) =>
                                                    setTextChatInactivityMinutes(event.target.value)
                                                }
                                                aria-invalid={!textChatInactivityIsValid}
                                                className="w-32"
                                            />
                                            <span className="text-sm text-muted-foreground">{copy("minutes")}</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground">{copy("End a text chat and trigger its completion webhook after this long without chat activity.")}</p>
                                        {!textChatInactivityIsValid && (
                                            <p className="text-xs text-destructive">
                                                {textChatInactivityValidationMessage}.
                                            </p>
                                        )}
                                    </div>
                                )}

                                {/* Embed Mode Selection */}
                                <div className="space-y-4">
                                    <Label>{copy("Embed Mode")}</Label>
                                    <div className="grid grid-cols-3 gap-4">
                                        <button
                                            type="button"
                                            onClick={() => setEmbedMode("floating")}
                                            className={`p-4 rounded-lg border-2 transition-all ${
                                                embedMode === "floating"
                                                    ? "border-primary bg-primary/5"
                                                    : "border-muted hover:border-muted-foreground/20"
                                            }`}
                                        >
                                            <div className="space-y-2">
                                                <div className="font-medium">{copy("Floating Widget")}</div>
                                                <div className="text-xs text-muted-foreground">{copy("Shows as a button in corner of the page")}</div>
                                            </div>
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setEmbedMode("inline")}
                                            className={`p-4 rounded-lg border-2 transition-all ${
                                                embedMode === "inline"
                                                    ? "border-primary bg-primary/5"
                                                    : "border-muted hover:border-muted-foreground/20"
                                            }`}
                                        >
                                            <div className="space-y-2">
                                                <div className="font-medium">{copy("Inline Component")}</div>
                                                <div className="text-xs text-muted-foreground">{copy("Embeds directly in your page content")}</div>
                                            </div>
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setEmbedMode("headless")}
                                            className={`p-4 rounded-lg border-2 transition-all ${
                                                embedMode === "headless"
                                                    ? "border-primary bg-primary/5"
                                                    : "border-muted hover:border-muted-foreground/20"
                                            }`}
                                        >
                                            <div className="space-y-2">
                                                <div className="font-medium">{copy("Headless (Bring Your Own UI)")}</div>
                                                <div className="text-xs text-muted-foreground">{copy("No UI - drive calls from your own buttons via the JS API")}</div>
                                            </div>
                                        </button>
                                    </div>
                                </div>

                                {/* Configuration based on mode */}
                                <div className="space-y-4">
                                    <Label>{copy("Configuration")}</Label>

                                    {/* Shared: Button Text + Button Color (skipped in headless — host renders its own UI) */}
                                    {embedMode !== "headless" && (
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="space-y-2">
                                                <Label htmlFor="button-text" className="text-sm">{copy("Button Text")}</Label>
                                                <Input
                                                    id="button-text"
                                                    value={buttonText}
                                                    onChange={(e) => setButtonText(e.target.value)}
                                                    placeholder={copy(WIDGET_TYPE_DEFAULTS[widgetType].buttonText)}
                                                    maxLength={40}
                                                />
                                            </div>
                                            <div className="space-y-2">
                                                <Label htmlFor="button-color" className="text-sm">{copy("Button Color")}</Label>
                                                <div className="flex gap-2">
                                                    <Input
                                                        id="button-color-picker"
                                                        type="color"
                                                        value={buttonColor}
                                                        onChange={(e) => setButtonColor(e.target.value)}
                                                        className="w-14 h-10 cursor-pointer"
                                                    />
                                                    <Input
                                                        id="button-color"
                                                        value={buttonColor}
                                                        onChange={(e) => setButtonColor(e.target.value)}
                                                        placeholder="#10b981"
                                                        className="flex-1"
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Floating mode: Position */}
                                    {embedMode === "floating" && (
                                        <div className="space-y-2">
                                            <Label htmlFor="position" className="text-sm">{copy("Position")}</Label>
                                            <Select value={position} onValueChange={setPosition}>
                                                <SelectTrigger id="position">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="bottom-right">{copy("Bottom Right")}</SelectItem>
                                                    <SelectItem value="bottom-left">{copy("Bottom Left")}</SelectItem>
                                                    <SelectItem value="top-right">{copy("Top Right")}</SelectItem>
                                                    <SelectItem value="top-left">{copy("Top Left")}</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    )}

                                    {/* Inline mode: Call to Action Text */}
                                    {embedMode === "inline" && (
                                        <div className="space-y-2">
                                            <Label htmlFor="cta-text" className="text-sm">{copy("Call to Action Text")}</Label>
                                            <Input
                                                id="cta-text"
                                                value={callToActionText}
                                                onChange={(e) => setCallToActionText(e.target.value)}
                                                placeholder={copy(WIDGET_TYPE_DEFAULTS[widgetType].callToActionText)}
                                            />
                                        </div>
                                    )}

                                    {/* Visitor-facing copy, so the widget can match the site's language.
                                        Headless renders no UI of ours, so it has nothing to translate. */}
                                    {embedMode !== "headless" && widgetType === "chat" && (
                                        <WidgetTextSection
                                            title={copy("Chat Panel Text")}
                                            description={copy("Wording visitors see inside the chat panel.")}
                                            groups={[{ fields: CHAT_TEXT_FIELDS }]}
                                            values={widgetTexts}
                                            defaults={widgetTextDefaults}
                                            onChange={handleWidgetTextChange}
                                        />
                                    )}

                                    {embedMode !== "headless" && widgetType === "voice" && (
                                        <WidgetTextSection
                                            title={copy("Voice Call Text")}
                                            description={
                                                embedMode === "inline"
                                                    ? copy("Wording visitors see on the call panel across the call lifecycle.")
                                                    : copy("Wording the call button cycles through while a call connects and runs.")
                                            }
                                            groups={
                                                embedMode === "inline"
                                                    ? [
                                                        { heading: "Button labels", fields: VOICE_BUTTON_TEXT_FIELDS },
                                                        { heading: "Status messages", fields: VOICE_STATUS_TEXT_FIELDS },
                                                    ]
                                                    : [{ fields: VOICE_BUTTON_TEXT_FIELDS }]
                                            }
                                            values={widgetTexts}
                                            defaults={widgetTextDefaults}
                                            onChange={handleWidgetTextChange}
                                        />
                                    )}

                                    {/* Preview (skipped for headless — host renders its own UI) */}
                                    {embedMode === "headless" ? null : embedMode === "floating" ? (
                                        <div className="rounded-lg border bg-muted/30 p-6 flex items-center justify-center">
                                            <button
                                                className="inline-flex items-center gap-2 rounded-full px-5 py-3 font-medium text-white shadow-lg whitespace-nowrap"
                                                style={{ backgroundColor: buttonColor }}
                                            >
                                                {widgetType === "chat" ? (
                                                    <MessageCircle className="h-4 w-4" />
                                                ) : (
                                                    <Mic className="h-4 w-4" />
                                                )}
                                                {buttonText || WIDGET_TYPE_DEFAULTS[widgetType].buttonText}
                                            </button>
                                        </div>
                                    ) : widgetType === "chat" ? (
                                        <div className="rounded-lg border bg-background p-6 flex items-center justify-center">
                                            <div className="w-full max-w-sm rounded-lg border shadow-sm overflow-hidden">
                                                <div
                                                    className="px-4 py-3 text-sm font-semibold text-white"
                                                    style={{ backgroundColor: buttonColor }}
                                                >
                                                    {buttonText || copy("Chat with Agent")}
                                                </div>
                                                <div className="p-4 space-y-2 bg-muted/20">
                                                    <div className="max-w-[80%] rounded-lg rounded-bl-sm bg-muted px-3 py-2 text-sm">{copy("Hi! How can I help you today?")}</div>
                                                    <div
                                                        className="max-w-[80%] ml-auto rounded-lg rounded-br-sm px-3 py-2 text-sm text-white"
                                                        style={{ backgroundColor: buttonColor }}
                                                    >{copy("I have a question…")}</div>
                                                </div>
                                                <div className="flex items-center gap-2 border-t px-3 py-2">
                                                    <div className="flex-1 rounded-md border bg-background px-3 py-1.5 text-sm text-muted-foreground">
                                                        {widgetTexts.chatInputPlaceholder?.trim()
                                                            || widgetTextDefaults?.chatInputPlaceholder}
                                                    </div>
                                                    <span
                                                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-white"
                                                        style={{ backgroundColor: buttonColor }}
                                                    >
                                                        <Send className="h-4 w-4" />
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="rounded-lg border bg-background p-6 flex items-center justify-center">
                                            <div className="text-center">
                                                <svg className="w-16 h-16 mx-auto mb-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                                    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                                                </svg>
                                                <p className="text-lg font-medium text-foreground mb-1">
                                                    {widgetTexts.voiceReadyTitle?.trim() || widgetTextDefaults?.voiceReadyTitle}
                                                </p>
                                                <p className="text-sm text-muted-foreground mb-5">{callToActionText}</p>
                                                <button
                                                    className="px-8 py-3 rounded-lg font-semibold text-white shadow-md"
                                                    style={{ backgroundColor: buttonColor }}
                                                >
                                                    {buttonText}
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Headless mode: Integration Instructions (chat) */}
                                    {embedMode === "headless" && widgetType === "chat" && (
                                        <div className="space-y-3">
                                            <div className="rounded-lg bg-muted/50 p-4">
                                                <h4 className="font-medium mb-2">{copy("Integration Instructions")}</h4>
                                                <ul className="text-sm space-y-2 text-muted-foreground">
                                                    <li>{copy("• Add the embed script tag to your page (see below).")}</li>
                                                    <li>{copy("• The widget renders no UI - render your own chat interface.")}</li>
                                                    <li>{copy("• Call ")}<code className="text-xs">window.DograhWidget.startChat()</code>{copy(" to start a conversation (the agent greeting arrives via ")}<code className="text-xs">onMessage</code>).</li>
                                                    <li>{copy("• Call ")}<code className="text-xs">window.DograhWidget.sendMessage(text)</code>{copy(" to send a visitor message; it resolves with the updated transcript, or ")}<code className="text-xs">null</code>{copy(" if the message could not be delivered.")}</li>
                                                    <li>{copy("• Call ")}<code className="text-xs">window.DograhWidget.endChat()</code>{copy(" to end the active conversation and trigger its completion webhook.")}</li>
                                                    <li>{copy("• Use ")}<code className="text-xs">getMessages()</code>{copy(" to read the transcript at any time.")}</li>
                                                    <li>{copy("• Subscribe to ")}<code className="text-xs">onMessage</code>{copy(" and ")}<code className="text-xs">onChatStateChange</code>{copy(" to drive your UI. States are ")}<code className="text-xs">idle</code>, <code className="text-xs">starting</code>, <code className="text-xs">ready</code>, <code className="text-xs">waiting</code>, <code className="text-xs">ended</code>, <code className="text-xs">expired</code>, <code className="text-xs">error</code>.</li>
                                                    <li>{copy("• Call ")}<code className="text-xs">window.DograhWidget.setContext({"{ ... }"})</code>{copy(" before ")}<code className="text-xs">startChat()</code>{copy(" to pass visitor details the page learned after load.")}</li>
                                                </ul>
                                            </div>

                                            <div className="rounded-lg bg-blue-50 dark:bg-blue-950/20 p-4 border border-blue-200 dark:border-blue-800">
                                                <h4 className="font-medium mb-2 text-blue-900 dark:text-blue-100">{copy("Example - drive your own chat UI")}</h4>
                                                <pre className="text-xs overflow-x-auto">
                                                    <code className="text-blue-800 dark:text-blue-200">{HEADLESS_CHAT_EXAMPLE}</code>
                                                </pre>
                                            </div>
                                        </div>
                                    )}

                                    {/* Headless mode: Integration Instructions (voice) */}
                                    {embedMode === "headless" && widgetType === "voice" && (
                                        <div className="space-y-3">
                                            <div className="rounded-lg bg-muted/50 p-4">
                                                <h4 className="font-medium mb-2">{copy("Integration Instructions")}</h4>
                                                <ul className="text-sm space-y-2 text-muted-foreground">
                                                    <li>{copy("• Add the embed script tag to your page (see below).")}</li>
                                                    <li>{copy("• The widget renders no UI - render your own buttons.")}</li>
                                                    <li>{copy("• Call ")}<code className="text-xs">window.DograhWidget.start()</code>{copy(" to begin a call.")}</li>
                                                    <li>{copy("• Call ")}<code className="text-xs">window.DograhWidget.end()</code>{copy(" to end it.")}</li>
                                                    <li>{copy("• Subscribe to ")}<code className="text-xs">onCallStart</code>, <code className="text-xs">onCallEnd</code>, <code className="text-xs">onStatusChange</code>, <code className="text-xs">onError</code>{copy(" to drive your UI.")}</li>
                                                    <li>• <code className="text-xs">start()</code>{copy(" must run inside a user-gesture handler (click) so the browser grants microphone access.")}</li>
                                                    <li>{copy("• Call ")}<code className="text-xs">window.DograhWidget.setContext({"{ ... }"})</code>{copy(" before ")}<code className="text-xs">start()</code>{copy(" to pass visitor details the page learned after load.")}</li>
                                                </ul>
                                            </div>

                                            <div className="rounded-lg bg-blue-50 dark:bg-blue-950/20 p-4 border border-blue-200 dark:border-blue-800">
                                                <h4 className="font-medium mb-2 text-blue-900 dark:text-blue-100">{copy("Example - track status in your own state")}</h4>
                                                <p className="text-xs text-blue-900/80 dark:text-blue-100/80 mb-2">{copy("Mirror the call status into a variable you control, then render whatever UI you like from it. The status values are ")}<code className="text-xs">idle</code>, <code className="text-xs">connecting</code>, <code className="text-xs">connected</code>, <code className="text-xs">failed</code>.
                                                </p>
                                                <pre className="text-xs overflow-x-auto">
                                                    <code className="text-blue-800 dark:text-blue-200">{`// Vanilla JS - keep your own state, render however you want
let callStatus = 'idle';

window.DograhWidget?.onStatusChange((status) => {
  callStatus = status;
  // ...trigger your render here (re-paint DOM, dispatch event, etc.)
});

document.getElementById('talk-btn').addEventListener('click', () => {
  if (callStatus === 'connected' || callStatus === 'connecting') {
    window.DograhWidget.end();
  } else {
    window.DograhWidget.start();
  }
});`}</code>
                                                </pre>
                                                <p className="text-xs text-blue-900/80 dark:text-blue-100/80 mt-3 mb-2">{copy("React:")}</p>
                                                <pre className="text-xs overflow-x-auto">
                                                    <code className="text-blue-800 dark:text-blue-200">{`function TalkButton() {
  const [status, setStatus] = useState('idle');

  useEffect(() => {
    window.DograhWidget?.onStatusChange(setStatus);
  }, []);

  const isLive = status === 'connected' || status === 'connecting';
  return (
    <button onClick={() => isLive ? window.DograhWidget.end() : window.DograhWidget.start()}>
      {/* render anything you want from \`status\` */}
    </button>
  );
}`}</code>
                                                </pre>
                                            </div>
                                        </div>
                                    )}

                                    {/* Inline mode: Integration Instructions */}
                                    {embedMode === "inline" && (
                                        <div className="space-y-3">
                                            <div className="rounded-lg bg-muted/50 p-4">
                                                <h4 className="font-medium mb-2">{copy("Integration Instructions")}</h4>
                                                <ul className="text-sm space-y-2 text-muted-foreground">
                                                    <li>{copy("• Add a div with id=\"dograh-inline-container\" where you want the widget")}</li>
                                                    <li>{copy("• The widget will render inside this container")}</li>
                                                    <li>{copy("• You have full control over the container's styling")}</li>
                                                    {widgetType === "chat" ? (
                                                        <li>{copy("• The chat panel renders in the container; the conversation starts when the visitor clicks the button")}</li>
                                                    ) : (
                                                        <>
                                                            <li>{copy("• Call window.DograhWidget.start() to begin the call")}</li>
                                                            <li>{copy("• Call window.DograhWidget.end() to end the call")}</li>
                                                        </>
                                                    )}
                                                </ul>
                                            </div>

                                            {widgetType === "chat" ? (
                                                <div className="rounded-lg bg-blue-50 dark:bg-blue-950/20 p-4 border border-blue-200 dark:border-blue-800">
                                                    <h4 className="font-medium mb-2 text-blue-900 dark:text-blue-100">{copy("Example")}</h4>
                                                    <pre className="text-xs overflow-x-auto">
                                                        <code className="text-blue-800 dark:text-blue-200">{`<h2>Chat with Our Agent</h2>
<div id="dograh-inline-container" style="min-height: 480px">
  <!-- Chat panel renders here; no extra JS needed -->
</div>`}</code>
                                                    </pre>
                                                </div>
                                            ) : (
                                                <div className="rounded-lg bg-blue-50 dark:bg-blue-950/20 p-4 border border-blue-200 dark:border-blue-800">
                                                    <h4 className="font-medium mb-2 text-blue-900 dark:text-blue-100">{copy("Example React Component")}</h4>
                                                    <pre className="text-xs overflow-x-auto">
                                                        <code className="text-blue-800 dark:text-blue-200">{`export function DograhAgent() {
  const [isCallActive, setIsCallActive] = useState(false);

  useEffect(() => {
    // Widget will auto-initialize when script loads
    window.DograhWidget?.onCallStart(() => {
      setIsCallActive(true);
    });
    window.DograhWidget?.onCallEnd(() => {
      setIsCallActive(false);
    });
  }, []);

  return (
    <div className="my-8">
      <h2>Talk to Our Agent</h2>
      <div id="dograh-inline-container" className="min-h-[400px]">
        {/* Widget renders here */}
      </div>
      <button
        onClick={() => window.DograhWidget?.start()}
        disabled={isCallActive}
      >
        Start Call
      </button>
    </div>
  );
}`}</code>
                                                    </pre>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>

                                <Separator />

                                {/* Save Button */}
                                <div className="flex justify-end">
                                    <Button
                                        onClick={handleSave}
                                        disabled={
                                            saving ||
                                            (widgetType === "chat" &&
                                                !textChatInactivityIsValid)
                                        }
                                    >
                                        {saving ? (
                                            <>
                                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />{copy("Saving...")}</>
                                        ) : (
                                            copy("Save Configurations")
                                        )}
                                    </Button>
                                </div>

                                {/* Embed Script (shows after saving; placeholder before) */}
                                {embedToken && embedToken.is_active ? (
                                    <>
                                        <Separator />
                                        <div className="space-y-3">
                                            <div className="flex items-center justify-between">
                                                <Label>{copy("Embed Code")}</Label>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() => copyToClipboard(embedToken.embed_script)}
                                                >
                                                    {copied ? (
                                                        <>
                                                            <Check className="h-4 w-4 mr-1" />{copy("Copied!")}</>
                                                    ) : (
                                                        <>
                                                            <Copy className="h-4 w-4 mr-1" />{copy("Copy Code")}</>
                                                    )}
                                                </Button>
                                            </div>
                                            <div className="relative">
                                                <pre className="bg-muted/50 rounded-lg p-4 text-xs overflow-x-auto whitespace-pre-wrap break-all">
                                                    <code>{embedToken.embed_script}</code>
                                                </pre>
                                            </div>
                                            <p className="text-xs text-muted-foreground">{copy("Add this script to your website's HTML to enable the widget. Configuration changes will apply automatically without re-embedding.")}</p>
                                            <p className="text-xs text-muted-foreground">{copy("To pass visitor details to the agent, edit the")}{" "}
                                                <code className="text-xs">data-dograh-context</code>{copy(" values above — or call")}{" "}
                                                <code className="text-xs">{"window.DograhWidget.setContext({ ... })"}</code>{copy(" for details your page learns later. Each one is available in your prompts as")}{" "}
                                                <code className="text-xs">{"{{initial_context.page_url}}"}</code>.{" "}
                                                <a
                                                    href={WIDGET_CONTEXT_DOC_URL}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="underline underline-offset-2 hover:text-foreground"
                                                >{copy("Learn more")}</a>
                                            </p>
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <Separator />
                                        <div className="space-y-3">
                                            <Label className="text-muted-foreground">{copy("Embed Code")}</Label>
                                            <div className="rounded-lg border border-dashed bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">{copy("Click ")}<span className="font-medium">{copy("Save Configurations")}</span>{copy(" to generate your embed script.")}</div>
                                        </div>
                                    </>
                                )}
                            </>
                        )}
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
