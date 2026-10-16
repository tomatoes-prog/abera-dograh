"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { PageShell } from "@/components/layout/PageShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrgConfig } from "@/context/OrgConfigContext";
import { useCopy } from "@/i18n/LocaleProvider";

import { LLMFallbackEditor } from "./LLMFallbackEditor";
import { useModelConnections } from "./useModelConnections";


export function LLMConfigurationPage({ configurationUuid }: { configurationUuid: string }) {
    const copy = useCopy();
    const { catalog, connections, configurations, loading, error, reload } = useModelConnections();
    const { refreshConfig } = useOrgConfig();
    const saved = configurations.find(item => item.uuid === configurationUuid && item.is_active);
    return <PageShell className="space-y-6">
        <Button asChild variant="ghost" className="-ml-3"><Link href={`/model-configurations/${configurationUuid}`}><ArrowLeft className="h-4 w-4" />{copy("Back to model configuration")}</Link></Button>
        {loading && !catalog ? <Skeleton className="h-80 w-full" /> : error ? <div role="alert" className="space-y-3 text-sm text-destructive"><p>{error}</p><Button variant="outline" onClick={() => void reload()}>{copy("Retry")}</Button></div>
            : !saved ? <p role="alert">{copy("This model configuration is unavailable.")}</p>
                : connections.find(item => item.uuid === saved.configuration.llm.provider_connection_uuid)?.provider === "dograh" ? <p role="alert">{copy("LLM fallbacks are unavailable in Dograh mode.")}</p>
                : catalog && <LLMFallbackEditor key={`${saved.uuid}-${saved.revision}`} saved={saved} catalog={catalog} connections={connections} onSaved={async () => {
                    await reload();
                    await refreshConfig();
                    toast.success(copy("LLM fallbacks saved"));
                }} />}
    </PageShell>;
}
