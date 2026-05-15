// ─── Zenic-Agents v3 — GET /api/v1/observability/traces ─────────────
// List traces with filters and pagination

import { NextRequest, NextResponse } from "next/server";
import { getTraceCollector } from "@/lib/observability/tracing/trace-collector";
import type { TraceQueryParams } from "@/lib/observability/types/tracing";

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;

    const params: TraceQueryParams = {
      traceId: searchParams.get("traceId") ?? undefined,
      sessionId: searchParams.get("sessionId") ?? undefined,
      decisionId: searchParams.get("decisionId") ?? undefined,
      tenantId: searchParams.get("tenantId") ?? undefined,
      status: (searchParams.get("status") as TraceQueryParams["status"]) ?? undefined,
      verdict: searchParams.get("verdict") ?? undefined,
      startDate: searchParams.get("startDate") ?? undefined,
      endDate: searchParams.get("endDate") ?? undefined,
      minDuration: searchParams.get("minDuration") ? Number(searchParams.get("minDuration")) : undefined,
      maxDuration: searchParams.get("maxDuration") ? Number(searchParams.get("maxDuration")) : undefined,
      page: searchParams.get("page") ? Number(searchParams.get("page")) : 1,
      pageSize: searchParams.get("pageSize") ? Number(searchParams.get("pageSize")) : 20,
      sortBy: (searchParams.get("sortBy") as TraceQueryParams["sortBy"]) ?? "createdAt",
      sortOrder: (searchParams.get("sortOrder") as TraceQueryParams["sortOrder"]) ?? "desc",
    };

    const collector = getTraceCollector();
    const result = await collector.queryTraces(params);

    return NextResponse.json({
      success: true,
      data: result.traces,
      total: result.total,
      page: result.page,
      pageSize: result.pageSize,
      totalPages: result.totalPages,
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to query traces" },
      { status: 500 },
    );
  }
}
