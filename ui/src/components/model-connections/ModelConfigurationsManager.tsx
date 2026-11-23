"use client";

import { Archive, ChevronRight, ExternalLink, Plus, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { archiveNamedModelConfiguration, restoreNamedModelConfiguration, setDefaultModelConfiguration } from "@/client/sdk.gen";
import { LIST_ROW_ACTIONS_CLASS, LIST_ROW_CLASS, LIST_ROW_TARGET_CLASS } from "@/components/layout/ListRow";
import { PageLayout, PageSection } from "@/components/layout/PageLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrgConfig } from "@/context/OrgConfigContext";
import { apiErrorMessage } from "@/i18n/errors";
import { useCopy } from "@/i18n/LocaleProvider";

import { configurationMode } from "./configuration";
import type { NamedModelConfiguration, ProviderConnection } from "./types";
import { MODE_LABELS, ROLE_LABELS, ROLES } from "./types";
import { useModelConnections } from "./useModelConnections";


function ConfigurationSummary({ configuration, connections }: { configuration: NamedModelConfiguration; connections: ProviderConnection[] }) {
    const copy = useCopy();
    const mode = configurationMode(configuration.configuration, connections);
    return <p className="text-sm text-muted-foreground">{copy(MODE_LABELS[mode])} · {mode === "dograh"
        ? connections.find(item => item.uuid === configuration.configuration.llm.provider_connection_uuid)?.name || copy("Unavailable connection")
        : ROLES.filter(role => configuration.configuration[role]).map(role => `${copy(ROLE_LABELS[role])}: ${configuration.configuration[role]?.settings.model || connections.find(item => item.uuid === configuration.configuration[role]?.provider_connection_uuid)?.name || copy("provider default")}`).join(" · ")}</p>;
}

export default function ModelConfigurationsManager({ docsUrl }: { docsUrl?: string }) {
    const copy = useCopy();
    const { catalog, connections, configurations, defaultUuid, loading, error, reload } = useModelConnections({ includeArchived: true });
    const { refreshConfig } = useOrgConfig();
    const [archive, setArchive] = useState<{ uuid: string; name: string } | null>(null);
    const [busy, setBusy] = useState(false);
    const [actionError, setActionError] = useState<string | null>(null);
    const [archivedOpen, setArchivedOpen] = useState(false);
    const [restoringUuid, setRestoringUuid] = useState<string | null>(null);

    const refresh = async () => { await reload(); await refreshConfig(); };
    const activeConfigurations = configurations.filter(item => item.is_active);
    const activeConnections = connections.filter(item => item.is_active);
    const archivedItems = configurations.filter(item => !item.is_active);

    const restore = async (uuid: string) => {
        setBusy(true); setRestoringUuid(uuid); setActionError(null);
        try {
            const response = await restoreNamedModelConfiguration({ path: { configuration_uuid: uuid } });
            if (response.error) throw new Error(apiErrorMessage(response.error, copy, "Unable to restore this item"));
            await refresh(); toast.success(copy("Restored"));
        } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Unable to restore this item"); }
        finally { setBusy(false); setRestoringUuid(null); }
    };

    return <PageLayout title={copy("Models")}
        description={<>{copy("Create named model configurations using your ")}<Link href="/provider-connections" className="underline">{copy("provider connections")}</Link> {copy(" in Realtime, Dograh, or BYOK mode.")}{docsUrl && <> <a href={docsUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline">{copy("Learn more")}<ExternalLink className="h-3 w-3" /></a></>}</>}
    >
        <PageSection title={copy("Named Model Configurations")} description={copy("Choose a setup for each workflow or make one your org default. Workflows inherit the default unless overridden.")}
            actions={<Button asChild><Link href="/model-configurations/new"><Plus className="h-4 w-4" />{copy("Add Configuration")}</Link></Button>}>
            {loading && !catalog && <div className="grid gap-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div>}
            {(error || actionError) && <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-destructive/40 p-4 text-sm text-destructive">
                <span>{actionError || error}</span>{error && <Button type="button" size="sm" variant="outline" onClick={() => void reload()}>{copy("Retry")}</Button>}
            </div>}
            {catalog && <>
                {activeConfigurations.length === 0 && <p className="rounded-md border border-dashed p-6 text-sm text-muted-foreground"><Link href="/provider-connections" className="underline">{copy("Add provider connections")}</Link>{copy(", then save your first named model configuration.")}</p>}
                <div className="space-y-4">
                    {activeConfigurations.map(configuration => {
                        return <div key={configuration.uuid} className={LIST_ROW_CLASS}>
                            <div className="min-w-0 flex-1 space-y-1">
                                <h3 className="flex flex-wrap items-center gap-2 font-medium">
                                    <Link href={`/model-configurations/${configuration.uuid}`} className={LIST_ROW_TARGET_CLASS}>{configuration.name}</Link>
                                    {defaultUuid === configuration.uuid && <Badge>{copy("Org default")}</Badge>}
                                </h3>
                                <ConfigurationSummary configuration={configuration} connections={connections} />
                            </div>
                            <div className={LIST_ROW_ACTIONS_CLASS}>
                                {defaultUuid !== configuration.uuid && <Button type="button" variant="outline" size="sm" disabled={busy || loading} onClick={async () => {
                                    setBusy(true); setActionError(null);
                                    try {
                                        const response = await setDefaultModelConfiguration({ body: { model_configuration_uuid: configuration.uuid } });
                                        if (response.error) throw new Error(apiErrorMessage(response.error, copy, "Failed to set organization default"));
                                        await refresh(); toast.success(copy("Organization default updated"));
                                    } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Failed to set organization default"); }
                                    finally { setBusy(false); }
                                }}>{copy("Make org default")}</Button>}
                                <Button asChild variant="ghost" size="sm"><Link href={`/model-configurations/${configuration.uuid}`}>{copy("Edit")}</Link></Button>
                                <Button asChild variant="ghost" size="sm"><Link href={`/model-configurations/new?duplicate=${configuration.uuid}`}>{copy("Duplicate")}</Link></Button>
                                <Button type="button" variant="ghost" size="sm" disabled={defaultUuid === configuration.uuid} onClick={() => { setActionError(null); setArchive({ uuid: configuration.uuid, name: configuration.name }); }}>{copy("Archive")}</Button>
                            </div>
                        </div>;
                    })}
                </div>
                {archivedItems.length > 0 && <Collapsible open={archivedOpen} onOpenChange={setArchivedOpen}>
                    <CollapsibleTrigger asChild>
                        <button type="button" aria-label={copy("Toggle Archived")} className="group flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-accent">
                            <ChevronRight size={16} className={`shrink-0 text-muted-foreground transition-transform duration-200 ${archivedOpen ? "rotate-90" : ""}`} />
                            <Archive size={16} className="shrink-0 text-muted-foreground" />
                            <span className="font-medium text-muted-foreground">{copy("Archived")}</span>
                            <Badge variant="secondary" className="ml-1 font-normal">{archivedItems.length}</Badge>
                        </button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="space-y-3 pt-3">
                        {archivedItems.map(item => {
                            const needsProviders = [
                                ...ROLES.map(role => item.configuration[role]),
                                ...(item.configuration.llm_fallback?.rules || []).map(rule => rule.target),
                            ].some(selection => {
                                return selection && !activeConnections.some(connection => connection.uuid === selection.provider_connection_uuid);
                            });
                            return <div key={item.uuid} className="flex flex-col justify-between gap-3 rounded-lg border p-4 sm:flex-row sm:items-center">
                                <div className="min-w-0 flex-1 space-y-1">
                                    <div className="opacity-60">
                                        <h3 className="font-medium">{item.name}</h3>
                                        <ConfigurationSummary configuration={item} connections={connections} />
                                    </div>
                                    {needsProviders && <p className="text-sm text-muted-foreground">{copy("Restore this configuration’s ")}<Link href="/provider-connections" className="underline">{copy("provider connections")}</Link> {copy(" first.")}</p>}
                                </div>
                                <div className="flex w-full flex-wrap items-center justify-end gap-1 sm:w-auto">
                                    <Button type="button" variant="outline" size="sm" disabled={busy || loading || needsProviders} onClick={() => void restore(item.uuid)}>
                                        <RotateCcw className="h-3.5 w-3.5" />{restoringUuid === item.uuid ? copy("Restoring…") : copy("Restore")}
                                    </Button>
                                </div>
                            </div>;
                        })}
                    </CollapsibleContent>
                </Collapsible>}
                <Dialog open={archive !== null} onOpenChange={open => { if (!open && !busy) setArchive(null); }}>
                    <DialogContent onOpenAutoFocus={() => undefined}>
                        <DialogHeader><DialogTitle>{copy("Archive ")}{archive?.name}?</DialogTitle><DialogDescription>{copy("Archived items cannot be selected for future runs. Items still referenced by active configurations or workflows must be unlinked first.")}</DialogDescription></DialogHeader>
                        {actionError && <p role="alert" className="text-sm text-destructive">{actionError}</p>}
                        <div className="flex justify-end gap-2"><Button variant="outline" disabled={busy} onClick={() => setArchive(null)}>{copy("Cancel")}</Button>
                            <Button disabled={busy} onClick={async () => {
                                if (!archive) return;
                                setBusy(true); setActionError(null);
                                try {
                                    const result = await archiveNamedModelConfiguration({ path: { configuration_uuid: archive.uuid } });
                                    if (result.error) throw new Error(apiErrorMessage(result.error, copy, "Unable to archive this item"));
                                    setArchive(null); await refresh(); toast.success(copy("Archived"));
                                } catch (cause) { setActionError(cause instanceof Error ? cause.message : "Unable to archive this item"); }
                                finally { setBusy(false); }
                            }}>{busy ? copy("Archiving…") : copy("Archive")}</Button>
                        </div>
                    </DialogContent>
                </Dialog>
            </>}
        </PageSection>
    </PageLayout>;
}
