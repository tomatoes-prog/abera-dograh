import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  const enabled = process.env.ENABLE_TELEMETRY === 'true';
  return NextResponse.json({
    enabled,
    dsn: enabled ? process.env.SENTRY_DSN || '' : '',
    environment: process.env.NODE_ENV || 'development',
  }, {
    headers: { 'Cache-Control': 'no-store' },
  });
}
