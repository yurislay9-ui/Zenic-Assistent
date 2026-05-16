// ─── Zenic-Agents v3 — GET /api/v1/observability/traces/[id] ────────
// Get a single trace with all its spans

import { NextRequest, NextResponse } from "next/server";
import { getTraceCollector } from "@/lib/observability/tracing/trace-collector";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const collector = getTraceCollector();
    const trace = await collector.getTrace(id);

    if (!trace) {
      return NextResponse.json(
        { success: false, error: "Trace not found" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: trace,
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to get trace" },
      { status: 500 },
    );
  }
}
