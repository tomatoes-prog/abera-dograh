"use client";

import { AlertCircle, CreditCard, ExternalLink, Key } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useCopy } from "@/i18n/LocaleProvider";


const SERVICE_KEYS_DOCS_URL = "https://docs.dograh.com/configurations/api-keys#service-keys";

interface ApiKeyErrorDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    error: string | null;
    errorCode: string | null;
    onNavigateToBilling: () => void;
    onNavigateToDevelopers: () => void;
    onNavigateToModelConfig: () => void;
}

export const ApiKeyErrorDialog = ({
    open,
    onOpenChange,
    error,
    errorCode,
    onNavigateToBilling,
    onNavigateToDevelopers,
    onNavigateToModelConfig,
}: ApiKeyErrorDialogProps) => {
    const copy = useCopy();
    const isBillingCreditsError = errorCode === 'insufficient_credits';
    const isServiceKeyOrgMismatch = errorCode === 'service_key_org_mismatch';
    const isQuotaError = isBillingCreditsError || errorCode === 'quota_exceeded';

    const title = isQuotaError
        ? copy("Insufficient Credits")
        : isServiceKeyOrgMismatch
            ? copy("Service Token Account Mismatch")
            : copy("API Configuration Error");
    const icon = isQuotaError ? <CreditCard className="h-5 w-5 text-orange-500" /> : <Key className="h-5 w-5 text-red-500" />;
    const buttonText = isBillingCreditsError
        ? copy("Go to Billing")
        : isServiceKeyOrgMismatch
            ? copy("Go to Developers")
            : copy("Go to Model Configurations");
    const onNavigate = isBillingCreditsError
        ? onNavigateToBilling
        : isServiceKeyOrgMismatch
            ? onNavigateToDevelopers
            : onNavigateToModelConfig;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {icon}
                        {title}
                    </DialogTitle>
                    <DialogDescription className="pt-3" asChild>
                        <div className="flex items-start gap-2">
                            <AlertCircle className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                            <div className="text-sm space-y-1">
                                <p className="font-medium text-foreground">{error}</p>
                                {isBillingCreditsError && (
                                    <p className="text-muted-foreground">{copy("Purchase credits from Billing to continue using Dograh-managed models.")}</p>
                                )}
                                {isServiceKeyOrgMismatch && (
                                    <a
                                        href={SERVICE_KEYS_DOCS_URL}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-0.5 text-muted-foreground underline"
                                    >{copy("Learn more ")}<ExternalLink className="h-3 w-3" />
                                    </a>
                                )}
                            </div>
                        </div>
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>{copy("Cancel")}</Button>
                    <Button onClick={onNavigate}>
                        {buttonText}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
