import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function getOnboardingConfig() {
  const baseUrl = process.env.ONBOARDING_API_URL?.trim();
  if (!baseUrl) return { enabled: false };

  try {
    const url = new URL(baseUrl);
    const hostname = url.hostname.replace(/^\[|\]$/g, "");
    const isLocalHttp =
      url.protocol === "http:" &&
      ["localhost", "127.0.0.1", "::1"].includes(hostname);
    if (
      (url.protocol !== "https:" && !isLocalHttp) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      return { enabled: false };
    }
    return {
      enabled: true,
      baseUrl: url.origin + url.pathname.replace(/\/+$/, ""),
    };
  } catch {
    return { enabled: false };
  }
}

export async function GET() {
  return NextResponse.json(getOnboardingConfig(), {
    headers: { "Cache-Control": "no-store" },
  });
}
