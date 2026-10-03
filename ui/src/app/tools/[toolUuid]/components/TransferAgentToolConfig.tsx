"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useCopy } from "@/i18n/LocaleProvider";


export interface TransferAgentWorkflowOption {
    id: number;
    name: string;
}

export interface TransferAgentToolConfigProps {
    name: string;
    onNameChange: (name: string) => void;
    description: string;
    onDescriptionChange: (description: string) => void;
    /** The agent this tool transfers to. */
    workflowId: string;
    onWorkflowIdChange: (workflowId: string) => void;
    /** Agents in this organization, offered as the destination. */
    workflows: TransferAgentWorkflowOption[];
    workflowsLoading?: boolean;
    message: string;
    onMessageChange: (message: string) => void;
    /** Whether the destination agent opens with its Start Call greeting. */
    playGreeting: boolean;
    onPlayGreetingChange: (playGreeting: boolean) => void;
}

export function TransferAgentToolConfig({
    name,
    onNameChange,
    description,
    onDescriptionChange,
    workflowId,
    onWorkflowIdChange,
    workflows,
    workflowsLoading = false,
    message,
    onMessageChange,
    playGreeting,
    onPlayGreetingChange,
}: TransferAgentToolConfigProps) {
    const copy = useCopy();
    return (
        <Card>
            <CardHeader>
                <CardTitle>{copy("Transfer To Agent Configuration")}</CardTitle>
                <CardDescription>{copy("Hands the live call to another agent. The caller stays connected, hears a ringer while the next agent is prepared, and the conversation so far is passed on as a handover note.")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                <div className="grid gap-2">
                    <Label htmlFor="transfer-agent-name">{copy("Tool Name")}</Label>
                    <Label className="text-xs text-muted-foreground">{copy("Also becomes the function name the agent calls. Name it after the destination, e.g. “Transfer to Billing”.")}</Label>
                    <Input
                        id="transfer-agent-name"
                        value={name}
                        onChange={(e) => onNameChange(e.target.value)}
                        placeholder={copy("e.g., Transfer to Billing")}
                    />
                </div>

                <div className="grid gap-2">
                    <Label htmlFor="transfer-agent-description">{copy("Description")}</Label>
                    <Label className="text-xs text-muted-foreground">{copy("This is what the agent decides on. To offer more than one destination, add a second transfer tool with its own description.")}</Label>
                    <Textarea
                        id="transfer-agent-description"
                        value={description}
                        onChange={(e) => onDescriptionChange(e.target.value)}
                        placeholder={copy("Use when the caller asks about an invoice, a payment or their balance")}
                        rows={3}
                    />
                </div>

                <div className="grid gap-2">
                    <Label htmlFor="transfer-agent-workflow">{copy("Transfer to agent")}</Label>
                    <Select value={workflowId} onValueChange={onWorkflowIdChange}>
                        <SelectTrigger id="transfer-agent-workflow">
                            <SelectValue
                                placeholder={
                                    workflowsLoading ? copy("Loading agents…") : copy("Select an agent")
                                }
                            />
                        </SelectTrigger>
                        <SelectContent>
                            {workflows.map((workflow) => (
                                <SelectItem key={workflow.id} value={String(workflow.id)}>
                                    {workflow.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                <div className="grid gap-2">
                    <Label htmlFor="transfer-agent-message">{copy("Handover message")}</Label>
                    <Label className="text-xs text-muted-foreground">{copy("Spoken in the current agent's own voice, and waited for before the caller is handed over. Leave empty to hand over without saying anything.")}</Label>
                    <Input
                        id="transfer-agent-message"
                        value={message}
                        onChange={(e) => onMessageChange(e.target.value)}
                        placeholder={copy("Let me connect you with the right person. One moment please.")}
                    />
                </div>

                <div className="flex items-center justify-between gap-4">
                    <div className="grid gap-1">
                        <Label htmlFor="transfer-agent-play-greeting">{copy("Play the destination agent's greeting")}</Label>
                        <p className="text-xs text-muted-foreground">{copy("Turn off to have the next agent continue the conversation instead of introducing itself. It then opens with a reply based on the handover note.")}</p>
                    </div>
                    <Switch
                        id="transfer-agent-play-greeting"
                        checked={playGreeting}
                        onCheckedChange={onPlayGreetingChange}
                    />
                </div>
            </CardContent>
        </Card>
    );
}
