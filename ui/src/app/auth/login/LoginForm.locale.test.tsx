import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/LocaleProvider";

import { LoginForm } from "./LoginForm";

const { login, errorToast } = vi.hoisted(() => ({ login: vi.fn(), errorToast: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({ loginApiV1AuthLoginPost: login }));
vi.mock("sonner", () => ({ toast: { error: errorToast } }));

beforeEach(() => vi.clearAllMocks());

it("shows Abera Cloud beside Dograh without the enterprise enquiry prompt", () => {
    render(<LocaleProvider initialLocale="es-419"><LoginForm signupEnabled /></LocaleProvider>);
    expect(screen.getAllByText("Abera Cloud")).toHaveLength(2);
    expect(screen.queryByText("Consulta para empresas")).toBeNull();
});

it("keeps login input values when the real auth language selector changes", () => {
    render(<LocaleProvider initialLocale="es-419"><LoginForm signupEnabled /></LocaleProvider>);
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "persona@example.com" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "test-only-value" } });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en" } });
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("persona@example.com");
    expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe("test-only-value");
    expect(login).not.toHaveBeenCalled();
});

it("shows a clear Spanish auth error when the SDK returns an HTTP failure", async () => {
    login.mockResolvedValue({ error: { detail: "Invalid email or password" } });
    render(<LocaleProvider initialLocale="es-419"><LoginForm signupEnabled /></LocaleProvider>);
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "persona@example.com" } });
    fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "test-only-value" } });
    fireEvent.submit(screen.getByRole("button", { name: "Iniciar sesión" }).closest("form")!);
    await waitFor(() => expect(errorToast).toHaveBeenCalledWith("Revisa tu correo y contraseña."));
    expect(screen.getByRole("button", { name: "Iniciar sesión" }).hasAttribute("disabled")).toBe(false);
});
