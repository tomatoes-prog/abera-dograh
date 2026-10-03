"use client";

import {
  AlertTriangle,
  ChevronRight,
  Copy,
  ExternalLink,
  Pencil,
  Plus,
  RotateCcw,
  Star,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  deleteTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdDelete,
  getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet,
  listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
  reactivateTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdReactivatePost,
  setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost,
} from "@/client/sdk.gen";
import type {
  TelephonyConfigurationDetail,
  TelephonyConfigurationListItem,
} from "@/client/types.gen";
import { ConfigFormDialog } from "@/components/telephony/ConfigFormDialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTelephonyConfigWarnings } from "@/context/TelephonyConfigWarningsContext";
import { useCopy } from "@/i18n/LocaleProvider";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";
import { copyTextToClipboard } from "@/lib/clipboard";


export default function TelephonyConfigurationsPage() {
    const copy = useCopy();
  const { user, getAccessToken, loading: authLoading } = useAuth();
  const searchParams = useSearchParams();
  const {
    telnyxMissingWebhookPublicKeyCount,
    vonageMissingSignatureSecretCount,
    refresh: refreshWarnings,
  } = useTelephonyConfigWarnings();
  const [items, setItems] = useState<TelephonyConfigurationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TelephonyConfigurationDetail | null>(
    null,
  );
  const [editOpen, setEditOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] =
    useState<TelephonyConfigurationListItem | null>(null);

  const fetchItems = useCallback(async () => {
    if (authLoading || !user) return;
    setLoading(true);
    try {
      const token = await getAccessToken();
      const res = await listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet(
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (res.error) throw new Error(copy(detailFromError(res.error)));
      setItems(res.data?.configurations ?? []);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : copy("Failed to load configurations"));
    } finally {
      setLoading(false);
    }
  }, [authLoading, user, getAccessToken, copy]);

  // After a save (create/update), webhook-verification warning state may have
  // changed — refresh the cached warning state so the page banner and nav badge
  // update without a manual reload.
  const onSaved = useCallback(async () => {
    await fetchItems();
    await refreshWarnings();
  }, [fetchItems, refreshWarnings]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // ?add=1 lands the user straight on the provider form — used by the Phone
  // Call dialog's "Add provider" action so the choice isn't asked twice.
  useEffect(() => {
    if (searchParams.get("add") === "1") setCreateOpen(true);
  }, [searchParams]);

  const onEdit = async (item: TelephonyConfigurationListItem) => {
    try {
      const token = await getAccessToken();
      const res = await getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: item.id },
        },
      );
      if (res.error) throw new Error(copy(detailFromError(res.error)));
      setEditTarget(res.data ?? null);
      setEditOpen(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : copy("Failed to load configuration"));
    }
  };

  const onSetDefault = async (item: TelephonyConfigurationListItem) => {
    try {
      const token = await getAccessToken();
      const res = await setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: item.id },
        },
      );
      if (res.error) throw new Error(copy(detailFromError(res.error)));
      toast.success(copy("{value0} is now the default outbound configuration", {value0: item.name}));
      fetchItems();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : copy("Failed to set default"));
    }
  };

  const onReactivate = async (item: TelephonyConfigurationListItem) => {
    try {
      const token = await getAccessToken();
      const res = await reactivateTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdReactivatePost(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: item.id },
        },
      );
      if (res.error) throw new Error(copy(detailFromError(res.error)));
      toast.success(copy("{value0} reactivated — reconnecting within a minute", {value0: item.name}));
      fetchItems();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : copy("Failed to reactivate configuration"),
      );
    }
  };

  const onConfirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      const token = await getAccessToken();
      const res = await deleteTelephonyConfigurationApiV1OrganizationsTelephonyConfigsConfigIdDelete(
        {
          headers: { Authorization: `Bearer ${token}` },
          path: { config_id: deleteTarget.id },
        },
      );
      if (res.error) throw new Error(copy(detailFromError(res.error)));
      toast.success(copy("Configuration deleted"));
      setDeleteTarget(null);
      fetchItems();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : copy("Failed to delete configuration"));
    }
  };

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-bold mb-2">{copy("Telephony configurations")}</h1>
            <p className="text-muted-foreground">{copy("Connect one or more telephony provider accounts. Each campaign uses one configuration; inbound calls are routed to the right one by account ID.")}{" "}
              <a
                href="https://docs.dograh.com/integrations/telephony/overview"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 underline"
              >{copy("Learn more ")}<ExternalLink className="h-3 w-3" />
              </a>
            </p>
          </div>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />{copy(" Add configuration")}</Button>
        </div>

        {telnyxMissingWebhookPublicKeyCount > 0 && (
          <div className="mb-6 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="space-y-1 text-sm">
                <p className="font-medium">{copy("Webhook public key not configured")}</p>
                <p>
                  {telnyxMissingWebhookPublicKeyCount === 1
                    ? copy("1 Telnyx configuration is")
                    : copy("{value0} Telnyx configurations are", {value0: telnyxMissingWebhookPublicKeyCount})}{" "}{copy("missing a webhook public key. Without it, Telnyx call status updates and inbound calls are being rejected. Copy your public key from")}{" "}
                  <span className="whitespace-nowrap">{copy("Mission Control Portal → Keys & Credentials → Public Key")}</span>{" "}{copy("and paste it into the affected Telnyx configuration below.")}</p>
              </div>
            </div>
          </div>
        )}

        {vonageMissingSignatureSecretCount > 0 && (
          <div className="mb-6 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="space-y-1 text-sm">
                <p className="font-medium">{copy("Signature secret not configured")}</p>
                <p>
                  {vonageMissingSignatureSecretCount === 1
                    ? copy("1 Vonage configuration is")
                    : copy("{value0} Vonage configurations are", {value0: vonageMissingSignatureSecretCount})}{" "}{copy("missing a signature secret. Without it, Vonage signed webhooks are rejected, so inbound calls and call status updates will not work. Copy the signature secret from your Vonage account and paste it into the affected Vonage configuration below.")}</p>
              </div>
            </div>
          </div>
        )}

        {loading ? (
          <div className="grid gap-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : items.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>{copy("No telephony configurations yet")}</CardTitle>
              <CardDescription>{copy("Add one to enable outbound calls and receive inbound calls.")}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />{copy(" Add configuration")}</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {items.map((item) => (
              <Card key={item.id}>
                <CardContent className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center">
                  <Link
                    href={`/telephony-configurations/${item.id}`}
                    className="flex flex-1 items-center gap-4 min-w-0"
                  >
                    <div className="flex flex-col gap-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{item.name}</span>
                        <Badge variant="secondary">{item.provider}</Badge>
                        {item.is_default_outbound && (
                          <Badge className="gap-1">
                            <Star className="h-3 w-3 fill-current" />{copy("Default")}</Badge>
                        )}
                        {item.inactive && (
                          <Badge variant="destructive">{copy("Inactive")}</Badge>
                        )}
                        {!item.inactive && item.is_ready_for_outbound === false && (
                          <Badge
                            variant="outline"
                            className="gap-1 border-amber-400 text-amber-700 dark:border-amber-700 dark:text-amber-400"
                          >
                            <AlertTriangle className="h-3 w-3" />{copy("Setup incomplete")}</Badge>
                        )}
                      </div>
                      <span className="text-sm text-muted-foreground">
                        {item.phone_number_count}{copy(" phone")}{" "}
                        {item.phone_number_count === 1 ? copy("number") : copy("numbers")}
                      </span>
                      {item.inactive && (
                        <span className="text-sm text-destructive">{copy("Disabled after repeated connection failures")}{item.inactive_reason ? copy(": {value0}", {value0: item.inactive_reason}) : ""}
                        </span>
                      )}
                      {!item.inactive && item.outbound_blocked_reason && (
                        <span className="text-sm text-amber-700 dark:text-amber-500">
                          {item.outbound_blocked_reason}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          copyTextToClipboard(String(item.id))
                            .then(() => toast.success(copy("Configuration ID copied")))
                            .catch(() => toast.error(copy("Failed to copy ID")));
                        }}
                        title={copy("Click to copy")}
                        className="inline-flex items-center gap-1 self-start rounded font-mono text-xs text-muted-foreground hover:text-foreground"
                      >
                        <span className="truncate">{copy("Configuration ID: ")}{item.id}</span>
                        <Copy className="h-3 w-3 shrink-0" />
                      </button>
                    </div>
                  </Link>
                  <div className="flex w-full flex-wrap items-center justify-end gap-1 sm:w-auto sm:flex-nowrap">
                    {item.inactive && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onReactivate(item)}
                        title={copy("Reconnect this configuration now")}
                      >
                        <RotateCcw className="h-4 w-4 mr-1" />{copy("Reactivate")}</Button>
                    )}
                    {!item.is_default_outbound && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onSetDefault(item)}
                        title={copy("Set as default outbound")}
                      >
                        <Star className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onEdit(item)}
                      title={copy("Edit")}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteTarget(item)}
                      title={copy("Delete")}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                    <Button variant="outline" size="sm" asChild>
                      <Link
                        href={`/telephony-configurations/${item.id}`}
                        aria-label={copy("Manage phone numbers for {value0}", {value0: item.name})}
                      >{copy("Manage Phone Numbers")}<ChevronRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <ConfigFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        existing={null}
        suggestDefaultOutbound={!items.some((item) => item.is_default_outbound)}
        onSaved={onSaved}
      />
      <ConfigFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        existing={editTarget}
        onSaved={onSaved}
      />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{copy("Delete configuration?")}</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget?.name}{copy(" and all of its phone numbers will be removed. Any campaigns that reference this configuration will block the deletion until they are reassigned.")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{copy("Cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirmDelete}>{copy("Delete")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
