// ─── Zenic-Agents v3 — GET /api/v1/observability/export/json ────────
// Export observability data in clean JSON format (traces + metrics)

import { NextRequest, NextResponse } from "next/server";
import { exportJson } from "@/lib/observability";
import type { ExportQueryParams } from "@/lib/observability";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    const params: ExportQueryParams = {
      format: "json",
      sessionId: searchParams.get("sessionId") ?? undefined,
      startDate: searchParams.get("startDate") ?? undefined,
      endDate: searchParams.get("endDate") ?? undefined,
      limit: searchParams.get("limit") ? Number(searchParams.get("limit")) : 100,
      includeTraces: searchParams.get("includeTraces") !== "false",
      includeMetrics: searchParams.get("includeMetrics") !== "false",
    };

    const traceIds = searchParams.get("traceIds");
    if (traceIds) {
      params.traceIds = traceIds.split(",");
    }

    const payload = await exportJson(params);

    return NextResponse.json(payload, {
      headers: {
        "Content-Type": "application/json",
        "X-Export-Format": "json",
        "X-Export-Version": "1.0.0",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "JSON export failed" },
      { status: 500 },
    );
  }
}
