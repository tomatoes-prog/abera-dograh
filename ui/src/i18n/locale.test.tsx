import { fireEvent, render, screen } from "@testing-library/react";
import { useCallback, useEffect, useState } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { PropertySpec, WidgetTexts } from "@/client/types.gen";
import { formatCalendarDate, formatDateTime } from "@/lib/dateTime";

import { copyFor } from "./catalog";
import { LOCALE_COOKIE, resolveUiLocale } from "./config";
import { apiErrorMessage } from "./errors";
import { languageDisplayName } from "./format";
import { LocaleProvider, useCopy } from "./LocaleProvider";
import { LocaleSwitcher } from "./LocaleSwitcher";
import sources from "./messages/sources.json";
import { localizeProperty } from "./schema";
import { newWidgetTextOverrides } from "./widget";

function Form({ load }: {load: () => void}) {
  const copy = useCopy();
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  useEffect(load, [load, copy]);
  const save = useCallback(() => setMessage(copy("Save")), [copy]);
  return <><LocaleSwitcher /><input aria-label="customer-name" value={name} onChange={e => setName(e.target.value)} />
    <button onClick={save}>{copy("Save")}</button><output>{message}</output></>;
}

describe("LATAM interface locale", () => {
  it("validates cookies and uses a runtime deployment default", () => {
    expect(resolveUiLocale("en", "es-419")).toBe("en");
    expect(resolveUiLocale("es-419", "en")).toBe("es-419");
    expect(resolveUiLocale("../../other", "en")).toBe("en");
    expect(resolveUiLocale(undefined, "bad")).toBe("es-419");
  });
  it("renders Spanish on the server and can render English in an independent request", () => {
    expect(renderToString(<LocaleProvider initialLocale="es-419"><Form load={() => {}} /></LocaleProvider>)).toContain("Guardar");
    expect(renderToString(<LocaleProvider initialLocale="en"><Form load={() => {}} /></LocaleProvider>)).toContain(">Save<");
  });
  it("switches locale without losing a dirty form or rerunning data effects", () => {
    const load = vi.fn();
    render(<LocaleProvider initialLocale="es-419"><Form load={load} /></LocaleProvider>);
    fireEvent.change(screen.getByLabelText("customer-name"), {target: {value: "Save {{customer_name}}"}});
    fireEvent.change(screen.getByRole("combobox"), {target: {value: "en"}});
    expect(screen.getByLabelText("customer-name").getAttribute("value")).toBe("Save {{customer_name}}");
    expect(screen.getByRole("button", {name: "Save"})).toBeTruthy();
    expect(document.cookie).toContain(LOCALE_COOKIE + "=en");
    expect(document.documentElement.lang).toBe("en");
    expect(load).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", {name: "Save"}));
    expect(screen.getByRole("status").textContent).toBe("Save");
    fireEvent.change(screen.getByRole("combobox"), {target: {value: "es-419"}});
    fireEvent.click(screen.getByRole("button", {name: "Guardar"}));
    expect(screen.getByRole("status").textContent).toBe("Guardar");
    expect(load).toHaveBeenCalledOnce();
  });
  it("formats every reviewed message without ICU errors and escapes code examples", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const locale of ["es-419", "en"] as const) {
      const copy = copyFor(locale);
      for (const source of Object.keys(sources)) {
        const result = copy(source, {value0: 2, value1: "s", value2: 10});
        expect(result.length, source).toBeGreaterThan(0);
      }
      expect(copy("{{initial_context.phone_number}}")).toBe("{{initial_context.phone_number}}");
      expect(copy("__proto__")).toBe("__proto__");
    }
    expect(copyFor("en")("Don't have an account?")).toBe("Don't have an account?");
    expect(error).not.toHaveBeenCalled();
    error.mockRestore();
  });
  it("uses whole-message plurals", () => {
    expect(copyFor("es-419")("{value0} voices", {value0: 1})).toBe("1 voz");
    expect(copyFor("es-419")("{value0} voices", {value0: 5})).toBe("5 voces");
  });
  it("localizes known auth errors and normalizes array-shaped or unknown failures", () => {
    const copy = copyFor("es-419");
    expect(apiErrorMessage({detail: "Invalid email or password"}, copy)).toBe("Revisa tu correo y contraseña.");
    expect(apiErrorMessage({detail: [{msg: "Field required", loc: ["body", "secret"]}]}, copy)).toBe("Ocurrió un error. Inténtalo de nuevo.");
    expect(apiErrorMessage({detail: "Private customer detail"}, copy)).not.toContain("Private customer detail");
  });
  it("localizes metadata without changing defaults, schema keys or option values", () => {
    const property: PropertySpec = {name: "prompt", type: "options", display_name: "System Prompt", description: "", default: "Save", options: [{label: "Always", value: "always"}], placeholder: "{{initial_context.phone_number}}"};
    const localized = localizeProperty(property, copyFor("es-419"));
    expect(localized.display_name).toBe("Instrucciones del agente");
    expect(localized.default).toBe("Save");
    expect(localized.name).toBe("prompt");
    expect(localized.options?.[0]).toEqual({label: "Siempre", value: "always"});
    expect(property.display_name).toBe("System Prompt");
  });
  it("builds new widget overrides from API defaults without modifying them", () => {
    const defaults = {endChatText: "End chat", voiceConnectedTitle: "Connected"} as WidgetTexts;
    expect(newWidgetTextOverrides(defaults, copyFor("es-419"))).toEqual({endChatText: "Finalizar chat", voiceConnectedTitle: "Conectado"});
    expect(defaults.endChatText).toBe("End chat");
    expect(newWidgetTextOverrides(null, copyFor("es-419"))).toEqual({});
  });
  it("formats display dates and languages without moving a calendar day", () => {
    expect(languageDisplayName("es", "es-419")).toBe("español");
    expect(languageDisplayName("multi", "es-419")).toContain("detección automática");
    expect(formatCalendarDate("2026-07-23", "es-419")).toContain("23");
    expect(formatCalendarDate("2026-07-23", "es-419")).toContain("jul");
    expect(formatDateTime("2026-07-23T03:00:00Z", "America/Bogota", "es-419")).toContain("22");
  });
});
