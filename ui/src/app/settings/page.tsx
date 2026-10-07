"use client";

import { ExternalLink } from "lucide-react";

import { CallEventsSection } from "@/components/CallEventsSection";
import { MCPSection } from "@/components/MCPSection";
import { OrganizationPreferencesSection } from "@/components/OrganizationPreferencesSection";
import { TelemetrySection } from "@/components/TelemetrySection";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useCopy } from "@/i18n/LocaleProvider";


export default function SettingsPage() {
    const copy = useCopy();
  return (
    <div className="flex justify-center py-12 px-4">
      <div className="w-full max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold">{copy("Platform Settings")}</h1>
          <p className="text-muted-foreground">{copy("Manage your platform configuration and integrations.")}</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{copy("Preferences")}</CardTitle>
            <CardDescription>{copy("Set organization-wide defaults such as the test phone number and timezone.")}</CardDescription>
          </CardHeader>
          <CardContent>
            <OrganizationPreferencesSection />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy("MCP Server")}</CardTitle>
            <CardDescription>{copy("Let AI agents access your Dograh workspace and documentation via the Model Context Protocol.")}{" "}
              <a
                href="https://docs.dograh.com/integrations/mcp"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 underline"
              >{copy("Learn more ")}<ExternalLink className="h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MCPSection />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{copy("Telemetry")}</CardTitle>
            <CardDescription>{copy("Configure Langfuse tracing for your voice agent calls.")}{" "}
              <a
                href="https://docs.dograh.com/configurations/tracing"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 underline"
              >{copy("Learn more ")}<ExternalLink className="h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TelemetrySection />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{copy("Call events")}</CardTitle>
            <CardDescription>{copy("Configure where your organization sends call diagnostics.")}</CardDescription>
          </CardHeader>
          <CardContent>
            <CallEventsSection />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
