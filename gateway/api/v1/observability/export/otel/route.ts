// ─── Zenic-Agents v3 — GET /api/v1/observability/export/otel ────────
// Export traces in OpenTelemetry Protocol (OTLP) JSON format
// Compatible with Grafana Tempo, Jaeger, and OTLP collectors

import { NextRequest, NextResponse } from "next/server";
import { exportOtel } from "@/lib/observability";
import type { ExportQueryParams } from "@/lib/observability";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    const params: ExportQueryParams = {
      format: "otlp_json",
      sessionId: searchParams.get("sessionId") ?? undefined,
      startDate: searchParams.get("startDate") ?? undefined,
      endDate: searchParams.get("endDate") ?? undefined,
      limit: searchParams.get("limit") ? Number(searchParams.get("limit")) : 100,
      includeTraces: true,
      includeMetrics: false,
    };

    const traceIds = searchParams.get("traceIds");
    if (traceIds) {
      params.traceIds = traceIds.split(",");
    }

    const payload = await exportOtel(params);

    return NextResponse.json(payload, {
      headers: {
        "Content-Type": "application/json",
        "X-Export-Format": "otlp-json",
        "X-Export-Version": "1.0.0",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "OTel export failed" },
      { status: 500 },
    );
  }
}
