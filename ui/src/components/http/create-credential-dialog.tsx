"use client";

import { AlertCircle, Loader2 } from "lucide-react";
import { useState } from "react";

import { createCredentialApiV1CredentialsPost, updateCredentialApiV1CredentialsCredentialUuidPut } from "@/client";
import { CredentialResponse, WebhookCredentialType } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
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
import { useCopy } from "@/i18n/LocaleProvider";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";


interface CreateCredentialDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onCreated?: (credential: CredentialResponse) => void;
    credential?: CredentialResponse;
    onUpdated?: (credential: CredentialResponse) => void;
}

interface CredentialField {
    key: string;
    label: string;
    placeholder: string;
    isSecret?: boolean;
}

const getCredentialDataFields = (type: WebhookCredentialType): CredentialField[] => {
    switch (type) {
        case "api_key":
            return [
                { key: "header_name", label: "Header Name", placeholder: "X-API-Key" },
                { key: "api_key", label: "API Key", placeholder: "your-api-key", isSecret: true },
            ];
        case "bearer_token":
            return [
                { key: "token", label: "Token", placeholder: "your-bearer-token", isSecret: true },
            ];
        case "basic_auth":
            return [
                { key: "username", label: "Username", placeholder: "username" },
                { key: "password", label: "Password", placeholder: "password", isSecret: true },
            ];
        case "custom_header":
            return [
                { key: "header_name", label: "Header Name", placeholder: "X-Custom-Header" },
                { key: "header_value", label: "Header Value", placeholder: "header-value", isSecret: true },
            ];
        default:
            return [];
    }
};

export function CreateCredentialDialog(props: CreateCredentialDialogProps) {
    // Unmount the form on close so secrets and errors never survive reopening.
    return props.open ? <CredentialDialogForm key={props.credential?.uuid ?? "new"} {...props} /> : null;
}

function CredentialDialogForm({
    open,
    onOpenChange,
    onCreated,
    credential,
    onUpdated,
}: CreateCredentialDialogProps) {
    const copy = useCopy();
    const { getAccessToken } = useAuth();

    const [name, setName] = useState(credential?.name ?? "");
    const [description, setDescription] = useState(credential?.description ?? "");
    const [credentialType, setCredentialType] = useState<WebhookCredentialType>(
        (credential?.credential_type as WebhookCredentialType) ?? "bearer_token"
    );
    const [credentialData, setCredentialData] = useState<Record<string, string>>({});
    const [replaceAuthentication, setReplaceAuthentication] = useState(false);
    const [isCreating, setIsCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const fields = getCredentialDataFields(credentialType);
    const needsAuthentication = !credential || replaceAuthentication;
    const canSave = name.trim() && (!needsAuthentication || fields.every(
        (field) => credentialData[field.key]?.trim()
    ));

    const handleCreate = async () => {
        if (!canSave || isCreating) return;

        setIsCreating(true);
        setError(null);

        try {
            const accessToken = await getAccessToken();
            const headers = { Authorization: `Bearer ${accessToken}` };
            const body = { name: name.trim(), description: description.trim() };
            const response = credential
                ? await updateCredentialApiV1CredentialsCredentialUuidPut({
                    headers,
                    path: { credential_uuid: credential.uuid },
                    body: {
                        ...body,
                        ...(replaceAuthentication ? {
                            credential_type: credentialType,
                            credential_data: credentialData,
                        } : {}),
                    },
                })
                : await createCredentialApiV1CredentialsPost({
                    headers,
                    body: { ...body, credential_type: credentialType, credential_data: credentialData },
                });

            if (response.error) {
                setError(detailFromError(response.error, copy("Failed to save credential")));
                return;
            }

            if (response.data) {
                if (credential) onUpdated?.(response.data);
                else onCreated?.(response.data);
                handleClose();
            }
        } catch (err) {
            setError(
                err instanceof Error ? err.message : copy("Failed to save credential")
            );
        } finally {
            setIsCreating(false);
        }
    };

    const handleClose = () => {
        onOpenChange(false);
    };

    const handleOpenChange = (newOpen: boolean) => {
        if (!isCreating) onOpenChange(newOpen);
    };

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>{credential ? copy("Edit Credential") : copy("Add Credential")}</DialogTitle>
                    <DialogDescription>
                        {credential
                            ? copy("Update this credential. Changes apply everywhere it is used.")
                            : copy("Create a credential for authenticating tools and webhooks.")}
                    </DialogDescription>
                </DialogHeader>

                {error && (
                    <div role="alert" className="flex items-start gap-2 p-3 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-md">
                        <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                        <span>{error}</span>
                    </div>
                )}

                <fieldset disabled={isCreating} className="min-w-0 space-y-4 py-4">
                    <div className="grid gap-2">
                        <Label htmlFor="cred-name">{copy("Name *")}</Label>
                        <Input
                            id="cred-name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder={copy("My API Key")}
                        />
                    </div>

                    <div className="grid gap-2">
                        <Label htmlFor="cred-description">{copy("Description")}</Label>
                        <Input
                            id="cred-description"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder={copy("Optional description")}
                        />
                    </div>

                    <div className="grid gap-2">
                        <Label htmlFor="cred-type">{copy("Credential Type")}</Label>
                        <Select
                            disabled={!!credential || isCreating}
                            value={credentialType}
                            onValueChange={(v) => {
                                setCredentialType(v as WebhookCredentialType);
                                setCredentialData({});
                            }}
                        >
                            <SelectTrigger id="cred-type" className="w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="none">{copy("No Authentication")}</SelectItem>
                                <SelectItem value="bearer_token">{copy("Bearer Token")}</SelectItem>
                                <SelectItem value="api_key">{copy("API Key")}</SelectItem>
                                <SelectItem value="basic_auth">{copy("Basic Auth")}</SelectItem>
                                <SelectItem value="custom_header">{copy("Custom Header")}</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {credential && fields.length > 0 && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <Checkbox
                                    id="replace-authentication"
                                    checked={replaceAuthentication}
                                    onCheckedChange={(checked) => {
                                        setReplaceAuthentication(checked === true);
                                        setCredentialData({});
                                    }}
                                />
                                <Label htmlFor="replace-authentication">{copy("Replace authentication details")}</Label>
                            </div>
                            <p className="text-xs text-muted-foreground">
                                {copy("Saved values are hidden. Leave this unchecked to keep them.")}</p>
                        </div>
                    )}

                    {needsAuthentication && fields.map((field) => (
                        <div key={field.key} className="grid gap-2">
                            <Label htmlFor={`cred-${field.key}`}>{field.label}</Label>
                            <Input
                                id={`cred-${field.key}`}
                                type={field.isSecret ? "password" : "text"}
                                autoComplete="off"
                                value={credentialData[field.key] || ""}
                                onChange={(e) =>
                                    setCredentialData((prev) => ({
                                        ...prev,
                                        [field.key]: e.target.value,
                                    }))
                                }
                                placeholder={field.placeholder}
                            />
                        </div>
                    ))}
                </fieldset>

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={handleClose}
                        disabled={isCreating}
                    >
                        {copy("Cancel")}</Button>
                    <Button
                        onClick={handleCreate}
                        disabled={!canSave || isCreating}
                    >
                        {isCreating ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                {copy("Saving...")}</>
                        ) : (
                            credential ? copy("Save Changes") : copy("Create")
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
