import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function getChatwootConfig() {
  const baseUrl = process.env.CHATWOOT_URL?.trim();
  const websiteToken = process.env.CHATWOOT_WEBSITE_TOKEN?.trim();
  if (!baseUrl || !websiteToken) return { enabled: false };

  try {
    const url = new URL(baseUrl);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.pathname !== "/" && url.pathname !== "")
    ) {
      return { enabled: false };
    }
    return { enabled: true, baseUrl: url.origin, websiteToken };
  } catch {
    return { enabled: false };
  }
}

export async function GET() {
  return NextResponse.json(getChatwootConfig(), {
    headers: { "Cache-Control": "no-store" },
  });
}
