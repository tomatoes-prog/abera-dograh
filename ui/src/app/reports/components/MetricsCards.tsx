"use client";

import { Phone,PhoneForwarded } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCopy } from "@/i18n/LocaleProvider";
import { useUiLocale } from "@/i18n/LocaleProvider";


interface MetricsCardsProps {
  metrics: {
    total_runs: number;
    xfer_count: number;
  };
}

export function MetricsCards({ metrics }: MetricsCardsProps) {
    const { locale } = useUiLocale();
    const copy = useCopy();
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{copy("Total Workflow Runs")}</CardTitle>
          <Phone className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{metrics.total_runs.toLocaleString(locale)}</div>
          <p className="text-xs text-muted-foreground">{copy("Total calls processed today")}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{copy("Transfer Dispositions")}</CardTitle>
          <PhoneForwarded className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{metrics.xfer_count.toLocaleString(locale)}</div>
          <p className="text-xs text-muted-foreground">{copy("Calls transferred (XFER)")}</p>
        </CardContent>
      </Card>
    </div>
  );
}
