import type { PropertySpec } from "@/client/types.gen";

import type { Copy } from "./catalog";

// Translate presentation only. Keep names, defaults, values and conditions.
export function localizeProperty(spec: PropertySpec, copy: Copy): PropertySpec {
  return {
    ...spec,
    display_name: copy(spec.display_name),
    description: spec.description ? copy(spec.description) : spec.description,
    placeholder: spec.placeholder ? copy(spec.placeholder) : spec.placeholder,
    properties: spec.properties?.map((property) => localizeProperty(property, copy)),
    options: spec.options?.map((option) => ({ ...option, label: copy(option.label) })),
  };
}
