"use client";

import { useEffect, useState } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCopy } from "@/i18n/LocaleProvider";


interface BodyTemplateEditorProps {
    value: Record<string, unknown> | null;
    onChange: (value: Record<string, unknown> | null) => void;
    onValidityChange: (valid: boolean) => void;
}

export function BodyTemplateEditor({
    value,
    onChange,
    onValidityChange,
}: BodyTemplateEditorProps) {
    const copy = useCopy();
    const [text, setText] = useState(value ? JSON.stringify(value, null, 2) : "");
    const [error, setError] = useState(false);

    useEffect(() => onValidityChange(true), [onValidityChange]);

    const handleChange = (next: string) => {
        setText(next);
        if (!next.trim()) {
            setError(false);
            onValidityChange(true);
            onChange(null);
            return;
        }

        try {
            const parsed: unknown = JSON.parse(next);
            if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
                throw new Error();
            }
            setError(false);
            onValidityChange(true);
            onChange(parsed as Record<string, unknown>);
        } catch {
            setError(true);
            onValidityChange(false);
        }
    };

    return (
        <div className="grid gap-2">
            <Label>{copy("JSON Body Template")}</Label>
            <Label className="text-xs text-muted-foreground">{copy("Use LLM parameters defined above with ")}{copy("{{defined_llm_parameter}}")}{copy(", or initial context with ")}{copy("{{initial_context.call_id}}")}.
            </Label>
            <Textarea
                className="min-h-48 font-mono text-xs"
                value={text}
                onChange={(event) => handleChange(event.target.value)}
                placeholder={
                    copy("{\n  \"customer\": {\n    \"id\": \"{{defined_llm_parameter}}\"\n  },\n  \"metadata\": {\n    \"call\": {\n      \"id\": \"{{initial_context.call_id}}\"\n    }\n  }\n}")
                }
                spellCheck={false}
            />
            {error && <p className="text-xs text-destructive">{copy("Enter a valid JSON object.")}</p>}
        </div>
    );
}
