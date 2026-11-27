'use client';

import { Bot, ChevronDown, LayoutTemplate, PlusIcon } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'sonner';

import { createWorkflowApiV1WorkflowCreateDefinitionPost } from '@/client/sdk.gen';
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Copy } from "@/i18n/catalog";
import type { UiLocale } from "@/i18n/config";
import { useCopy, useUiLocale } from "@/i18n/LocaleProvider";
import { useAuth } from '@/lib/auth';
import logger from '@/lib/logger';
import { getRandomId } from '@/lib/utils';


const BLANK_WORKFLOW_PROMPTS: Record<UiLocale, string> = {
    en: `# Goal
You are a helpful agent who is handing a conversation over voice with a human. This is a voice conversation, so transcripts can be error prone.

## Rules
- Language: UK English but does not have to be correct english
- Keep responses short and 2-3 sentences max
- If you have to repeat something that you said in your previous two turns, then rephrase a bit while keeping the same meaning. Never repeat the exact same words as in your previous 2 responses.

## Speech Handling
- There could be multiple transcription errors.
- Accept variations: yes/yeah/yep/aye, no/nah/nope
- If user says "sorry?" or "pardon me" or "can you repeat"  or "what?", they might not have heard you- so just repeat what you just said.

### Flow
Start by saying "Hi". Be polite and courteous.`,
    "es-419": `# Objetivo
Eres un agente útil que atiende una conversación de voz con una persona. Las transcripciones pueden contener errores.

## Reglas
- Idioma: español latinoamericano. Usa expresiones naturales y ten en cuenta que la transcripción puede tener errores.
- Mantén las respuestas breves, con un máximo de 2 o 3 oraciones.
- Si debes repetir algo que dijiste en tus dos turnos anteriores, exprésalo de otra forma sin cambiar el sentido. No repitas exactamente las mismas palabras de tus dos respuestas anteriores.

## Manejo de la voz
- La transcripción puede contener varios errores.
- Acepta variantes: sí, ajá, claro o de acuerdo; no, nop o para nada.
- Si la persona dice «¿perdón?», «¿me repites?» o «¿qué?», puede que no te haya escuchado. Repite lo que acabas de decir.

### Flujo
Empieza diciendo «Hola». Sé amable y cortés.`,
};

function createBlankWorkflowDefinition(locale: UiLocale, copy: Copy) {
    return {
        nodes: [
            {
                id: "1",
                type: "startCall",
                position: { x: 175, y: 60 },
                data: {
                    greeting: copy("Hey There! How can I help you today?"),
                    prompt: BLANK_WORKFLOW_PROMPTS[locale],
                    name: copy("start call"),
                    allow_interrupt: true,
                    invalid: false,
                    validationMessage: null,
                    add_global_prompt: false,
                    delayed_start: false,
                    is_start: true,
                    selected_through_edge: false,
                    hovered_through_edge: false,
                    extraction_enabled: false,
                    selected: false,
                    dragging: false,
                },
            },
        ],
        edges: [],
        viewport: { x: 808, y: 269, zoom: 0.75 },
    };
}

export function CreateWorkflowButton() {
    const copy = useCopy();
    const { locale } = useUiLocale();
    const router = useRouter();
    const { user, getAccessToken } = useAuth();
    const [isCreating, setIsCreating] = useState(false);

    const handleAgentBuilder = () => {
        router.push('/workflow/create');
    };

    const handleBlankCanvas = async () => {
        if (isCreating || !user) return;
        setIsCreating(true);

        try {
            const accessToken = await getAccessToken();
            const name = copy("Workflow-{value0}", { value0: getRandomId() });
            const response = await createWorkflowApiV1WorkflowCreateDefinitionPost({
                body: {
                    name,
                    workflow_definition: createBlankWorkflowDefinition(locale, copy) as unknown as { [key: string]: unknown },
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                },
            });

            if (response.data?.id) {
                router.push(`/workflow/${response.data.id}`);
            }
        } catch (err) {
            logger.error(`Error creating blank workflow: ${err}`);
            toast.error(copy("Failed to create workflow"));
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button disabled={isCreating}>
                    <PlusIcon className="w-4 h-4" />
                    {isCreating ? copy("Creating...") : copy("Create Agent")}
                    <ChevronDown className="w-4 h-4" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={handleAgentBuilder} className="cursor-pointer">
                    <Bot className="w-4 h-4 mr-2" />
                    <div>
                        <div className="font-medium">{copy("Use Agent Builder")}</div>
                        <div className="text-xs text-muted-foreground">{copy("AI generates a workflow from your description")}</div>
                    </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleBlankCanvas} disabled={isCreating} className="cursor-pointer">
                    <LayoutTemplate className="w-4 h-4 mr-2" />
                    <div>
                        <div className="font-medium">{copy("Blank Canvas")}</div>
                        <div className="text-xs text-muted-foreground">{copy("Start from scratch with an empty workflow")}</div>
                    </div>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
