"use client";

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { getCampaignTrafficStatsApiV1CampaignCampaignIdTrafficStatsGet } from '@/client/sdk.gen';
import type { CampaignResponse, CampaignTrafficStatsResponse } from '@/client/types.gen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useCopy } from "@/i18n/LocaleProvider";
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';


export default function CampaignTrafficStats({ campaign }: { campaign: CampaignResponse }) {
    const copy = useCopy();
    const { user, loading } = useAuth();
    const [stats, setStats] = useState<CampaignTrafficStatsResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [refresh, setRefresh] = useState(0);
    const revision = campaign.traffic_split?.revision;
    useEffect(() => {
        if (loading || !user) return;
        let cancelled = false;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const fetchStats = async () => {
            try {
                const response = await getCampaignTrafficStatsApiV1CampaignCampaignIdTrafficStatsGet({ path: { campaign_id: campaign.id } });
                if (cancelled) return;
                if (response.error) throw new Error(copy(detailFromError(response.error, 'Failed to load traffic statistics')));
                setStats(response.data ?? null);
                setError(null);
            } catch (e) {
                if (!cancelled) setError(e instanceof Error ? e.message : copy("Failed to load traffic statistics"));
            } finally {
                if (!cancelled && ['running', 'syncing'].includes(campaign.state)) timer = setTimeout(fetchStats, 10000);
            }
        };
        fetchStats();
        return () => { cancelled = true; clearTimeout(timer); };
    }, [campaign.id, campaign.state, revision, loading, user, refresh, copy]);

    return <Card>
        <CardHeader>
            <div className="flex justify-between items-center gap-3"><CardTitle>{copy("Traffic split")}</CardTitle><Button type="button" variant="outline" size="sm" onClick={() => setRefresh(r => r + 1)}>{copy("Refresh")}</Button></div>
            <CardDescription>{copy("Target is the current split. Actual share includes all call attempts and retries, including earlier splits. Small campaigns may differ from the target.")}</CardDescription>
        </CardHeader>
        <CardContent>
            {error && <p role="alert" className="text-sm text-destructive mb-3">{error}</p>}
            {!stats ? <p className="text-sm text-muted-foreground">{error ? copy("Statistics unavailable.") : copy("Loading traffic statistics…")}</p> : <Table>
                <TableHeader><TableRow><TableHead>{copy("Agent / version")}</TableHead><TableHead>{copy("Target")}</TableHead><TableHead>{copy("Actual")}</TableHead><TableHead>{copy("Completed attempts")}</TableHead><TableHead>{copy("Outcomes")}</TableHead></TableRow></TableHeader>
                <TableBody>{stats.variants.map(variant => <TableRow key={variant.id}>
                    <TableCell>
                        <Link className="underline" href={`/workflow/${variant.workflow_id}${variant.workflow_definition_id == null ? '?version=latest' : variant.version_number != null ? `?version=${variant.version_number}` : ''}`}>{variant.workflow_name}</Link>
                        <div className="text-sm text-muted-foreground">{variant.workflow_definition_id == null ? copy("Latest published") : copy("Version {value0}", {value0: variant.version_number ?? variant.workflow_definition_id})}</div>
                        {variant.workflow_definition_id == null && (variant.definitions?.length ?? 0) > 0 && <div className="text-xs text-muted-foreground">{(variant.definitions ?? []).map((d, index) => <span key={d.definition_id ?? 'unversioned'}>{index > 0 && ' · '}{d.version_number != null ? <Link className="underline" href={`/workflow/${variant.workflow_id}?version=${d.version_number}`}>v{d.version_number}</Link> : copy("Unversioned")}: {d.attempts}</span>)}</div>}
                    </TableCell>
                    <TableCell>{variant.target_weight == null ? copy("Removed") : copy("{value0}%", {value0: variant.target_weight})}</TableCell>
                    <TableCell>{(variant.actual_percentage ?? 0).toFixed(1)}%</TableCell>
                    <TableCell>{variant.completed} / {variant.attempts}</TableCell>
                    <TableCell className="text-sm">{Object.entries(variant.outcomes ?? {}).map(([outcome, count]) => `${outcome.replaceAll('_', ' ')}: ${count}`).join(' · ') || copy("No attempts yet")}</TableCell>
                </TableRow>)}</TableBody>
            </Table>}
        </CardContent>
    </Card>;
}
