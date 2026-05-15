// ─── Zenic-Agents v3 — GET /api/v1/observability/metrics/business ───
// Business metrics: DENY rate, approval rate, cost, time to decision, savings

import { NextRequest, NextResponse } from "next/server";
import { collectBusinessMetrics } from "@/lib/observability";
import type { MetricTimeRange } from "@/lib/observability";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const from = searchParams.get("from") ?? undefined;
    const to = searchParams.get("to") ?? "now";

    const timeRange: MetricTimeRange | undefined = from
      ? { from, to }
      : undefined;

    const metrics = await collectBusinessMetrics(timeRange);

    return NextResponse.json({
      success: true,
      data: metrics,
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to collect business metrics" },
      { status: 500 },
    );
  }
}
