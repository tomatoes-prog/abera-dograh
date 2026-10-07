"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";

import type { ToolParameter as ApiToolParameter } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
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
import { useCopy } from "@/i18n/LocaleProvider";


export type ParameterType = ApiToolParameter["type"];

export interface ToolParameter {
    name: string;
    type: ParameterType;
    description: string;
    required: boolean;
}

export interface PresetToolParameter {
    name: string;
    type: ParameterType;
    valueTemplate: string;
    required: boolean;
}

interface ParameterEditorProps {
    parameters: ToolParameter[];
    onChange: (parameters: ToolParameter[]) => void;
    disabled?: boolean;
}

export function ParameterEditor({
    parameters,
    onChange,
    disabled = false,
}: ParameterEditorProps) {
    const copy = useCopy();
    const addParameter = () => {
        onChange([
            ...parameters,
            { name: "", type: "string", description: "", required: true },
        ]);
    };

    const updateParameter = (
        index: number,
        field: keyof ToolParameter,
        value: string | boolean
    ) => {
        const newParams = [...parameters];
        newParams[index] = { ...newParams[index], [field]: value };
        onChange(newParams);
    };

    const removeParameter = (index: number) => {
        onChange(parameters.filter((_, i) => i !== index));
    };

    return (
        <div className="space-y-4">
            {parameters.length === 0 && (
                <div className="text-sm text-muted-foreground py-4 text-center border border-dashed rounded-md">{copy("No parameters defined. Add a parameter to specify what data this tool needs.")}</div>
            )}

            {parameters.map((param, index) => (
                <div
                    key={index}
                    className="border rounded-lg p-4 space-y-3 bg-muted/20"
                >
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-muted-foreground">{copy("Parameter ")}{index + 1}
                        </span>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => removeParameter(index)}
                            disabled={disabled}
                            className="h-8 w-8"
                        >
                            <Trash2Icon className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                        </Button>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                            <Label className="text-xs">{copy("Name")}</Label>
                            <Label className="text-xs text-muted-foreground">{copy("Name of the parameter, like \"order_id\" or \"customer_name\"")}</Label>
                            <Input
                                placeholder={copy("e.g., customer_name")}
                                value={param.name}
                                onChange={(e) =>
                                    updateParameter(index, "name", e.target.value)
                                }
                                disabled={disabled}
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs">{copy("Type")}</Label>
                            <Label className="text-xs text-muted-foreground">{copy("Type of the parameter, like \"string\" or \"number\" or \"boolean\"")}</Label>
                            <Select
                                value={param.type}
                                onValueChange={(value: ParameterType) =>
                                    updateParameter(index, "type", value)
                                }
                                disabled={disabled}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder={copy("Select type")} />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="string">{copy("String")}</SelectItem>
                                    <SelectItem value="number">{copy("Number")}</SelectItem>
                                    <SelectItem value="boolean">{copy("Boolean")}</SelectItem>
                                    <SelectItem value="object">{copy("Object")}</SelectItem>
                                    <SelectItem value="array">{copy("Array")}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="space-y-1.5">
                        <Label className="text-xs">{copy("Description")}</Label>
                        <Label className="text-xs text-muted-foreground">{copy("Description of the parameter, which makes it easy for LLM to understand, like \"The ID of the Customer to fetch Order Details\"")}</Label>
                        <Input
                            placeholder={copy("Describe what this parameter is for...")}
                            value={param.description}
                            onChange={(e) =>
                                updateParameter(index, "description", e.target.value)
                            }
                            disabled={disabled}
                        />
                    </div>

                    <div className="flex items-center gap-2">
                        <Switch
                            id={`required-${index}`}
                            checked={param.required}
                            onCheckedChange={(checked) =>
                                updateParameter(index, "required", checked)
                            }
                            disabled={disabled}
                        />
                        <Label htmlFor={`required-${index}`} className="text-sm">{copy("Required")}</Label>
                    </div>
                </div>
            ))}

            <Button
                variant="outline"
                size="sm"
                onClick={addParameter}
                className="w-fit"
                disabled={disabled}
            >
                <PlusIcon className="h-4 w-4 mr-1" />{copy(" Add Parameter")}</Button>
        </div>
    );
}

interface PresetParameterEditorProps {
    parameters: PresetToolParameter[];
    onChange: (parameters: PresetToolParameter[]) => void;
    disabled?: boolean;
}

export function PresetParameterEditor({
    parameters,
    onChange,
    disabled = false,
}: PresetParameterEditorProps) {
    const copy = useCopy();
    const addParameter = () => {
        onChange([
            ...parameters,
            { name: "", type: "string", valueTemplate: "", required: true },
        ]);
    };

    const updateParameter = (
        index: number,
        field: keyof PresetToolParameter,
        value: string | boolean
    ) => {
        const newParams = [...parameters];
        newParams[index] = { ...newParams[index], [field]: value };
        onChange(newParams);
    };

    const removeParameter = (index: number) => {
        onChange(parameters.filter((_, i) => i !== index));
    };

    return (
        <div className="space-y-4">
            {parameters.length === 0 && (
                <div className="text-sm text-muted-foreground py-4 text-center border border-dashed rounded-md">{copy("No preset parameters defined. Add one to inject a fixed value or workflow context into the request.")}</div>
            )}

            {parameters.map((param, index) => (
                <div
                    key={index}
                    className="border rounded-lg p-4 space-y-3 bg-muted/20"
                >
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-muted-foreground">{copy("Preset Parameter ")}{index + 1}
                        </span>
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => removeParameter(index)}
                            disabled={disabled}
                            className="h-8 w-8"
                        >
                            <Trash2Icon className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                        </Button>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                            <Label className="text-xs">{copy("Name")}</Label>
                            <Label className="text-xs text-muted-foreground">{copy("Key sent to the API, like \"phone_number\" or \"customer_id\"")}</Label>
                            <Input
                                placeholder={copy("e.g., phone_number")}
                                value={param.name}
                                onChange={(e) =>
                                    updateParameter(index, "name", e.target.value)
                                }
                                disabled={disabled}
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-xs">{copy("Type")}</Label>
                            <Label className="text-xs text-muted-foreground">{copy("JSON type to send to the API")}</Label>
                            <Select
                                value={param.type}
                                onValueChange={(value: ParameterType) =>
                                    updateParameter(index, "type", value)
                                }
                                disabled={disabled}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder={copy("Select type")} />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="string">{copy("String")}</SelectItem>
                                    <SelectItem value="number">{copy("Number")}</SelectItem>
                                    <SelectItem value="boolean">{copy("Boolean")}</SelectItem>
                                    <SelectItem value="object">{copy("Object")}</SelectItem>
                                    <SelectItem value="array">{copy("Array")}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="space-y-1.5">
                        <Label className="text-xs">{copy("Value or Template")}</Label>
                        <Label className="text-xs text-muted-foreground">{copy("Use a fixed value or a template like ")}{copy("{{initial_context.phone_number}}")}{copy(" or ")}{copy("{{gathered_context.customer_id}}")}
                        </Label>
                        <Input
                            placeholder={copy("e.g., {{initial_context.phone_number}}")}
                            value={param.valueTemplate}
                            onChange={(e) =>
                                updateParameter(index, "valueTemplate", e.target.value)
                            }
                            disabled={disabled}
                        />
                    </div>

                    <div className="flex items-center gap-2">
                        <Switch
                            id={`preset-required-${index}`}
                            checked={param.required}
                            onCheckedChange={(checked) =>
                                updateParameter(index, "required", checked)
                            }
                            disabled={disabled}
                        />
                        <Label htmlFor={`preset-required-${index}`} className="text-sm">{copy("Required")}</Label>
                    </div>
                </div>
            ))}

            <Button
                variant="outline"
                size="sm"
                onClick={addParameter}
                className="w-fit"
                disabled={disabled}
            >
                <PlusIcon className="h-4 w-4 mr-1" />{copy(" Add Preset Parameter")}</Button>
        </div>
    );
}
