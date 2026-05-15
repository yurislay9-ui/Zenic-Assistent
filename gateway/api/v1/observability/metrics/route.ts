// ─── Zenic-Agents v3 — GET /api/v1/observability/metrics ────────────
// Get all observability metrics (business + security + resilience)

import { NextRequest, NextResponse } from "next/server";
import { collectAllMetrics, collectMetricsByCategory } from "@/lib/observability";
import type { MetricTimeRange } from "@/lib/observability";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const category = searchParams.get("category") ?? undefined;
    const from = searchParams.get("from") ?? undefined;
    const to = searchParams.get("to") ?? "now";
    const interval = searchParams.get("interval") ?? undefined;

    const timeRange: MetricTimeRange | undefined = from
      ? { from, to, interval: interval ?? undefined }
      : undefined;

    const metrics = category
      ? await collectMetricsByCategory(category as "business" | "security" | "resilience" | "operational", timeRange)
      : await collectAllMetrics(timeRange);

    return NextResponse.json({
      success: true,
      data: metrics,
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to collect metrics" },
      { status: 500 },
    );
  }
}
