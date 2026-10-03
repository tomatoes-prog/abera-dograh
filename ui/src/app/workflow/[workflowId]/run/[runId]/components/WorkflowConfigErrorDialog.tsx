"use client";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useCopy } from "@/i18n/LocaleProvider";


interface WorkflowConfigErrorProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    error: string | null;
    onNavigateToWorkflow: () => void;
}

export const WorkflowConfigErrorDialog = ({
    open,
    onOpenChange,
    error,
    onNavigateToWorkflow
}: WorkflowConfigErrorProps) => {
    const copy = useCopy();
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{copy("Workflow Error")}</DialogTitle>
                    <DialogDescription className="text-red-500 whitespace-pre-line">
                        {error}
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button onClick={onNavigateToWorkflow}>{copy("Go to Workflow")}</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
