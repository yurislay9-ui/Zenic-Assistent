// ─── Zenic-Agents v3 — POST /api/v1/observability/spans ─────────────
// Ingest completed spans into the trace system

import { NextRequest, NextResponse } from "next/server";
import { getTraceCollector } from "@/lib/observability/tracing/trace-collector";
import type { SpanRecord } from "@/lib/observability/types/tracing";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.spans || !Array.isArray(body.spans)) {
      return NextResponse.json(
        { success: false, error: "Request body must include a 'spans' array" },
        { status: 400 },
      );
    }

    const spans: SpanRecord[] = body.spans.map((s: Record<string, unknown>) => ({
      id: "",
      spanId: s.spanId as string,
      traceId: s.traceId as string,
      parentSpanId: (s.parentSpanId as string) ?? null,
      name: s.name as string,
      kind: (s.kind as SpanRecord["kind"]) ?? "internal",
      status: (s.status as SpanRecord["status"]) ?? "ok",
      statusMessage: (s.statusMessage as string) ?? null,
      startTime: new Date(s.startTime as string),
      endTime: s.endTime ? new Date(s.endTime as string) : null,
      duration: (s.duration as number) ?? null,
      service: (s.service as string) ?? "zenic-gateway",
      resource: (s.resource as string) ?? null,
      resourceId: (s.resourceId as string) ?? null,
      action: (s.action as string) ?? null,
      outcome: (s.outcome as SpanRecord["outcome"]) ?? null,
      attributes: (s.attributes as Record<string, unknown>) ?? {},
      events: (s.events as SpanRecord["events"]) ?? [],
      links: (s.links as SpanRecord["links"]) ?? [],
      createdAt: new Date(),
    }));

    const collector = getTraceCollector();

    if (spans.length === 1) {
      await collector.ingestSpan(spans[0]);
    } else {
      await collector.ingestSpanBatch(spans);
    }

    return NextResponse.json({
      success: true,
      data: { ingested: spans.length },
      message: `Ingested ${spans.length} span(s)`,
    });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Failed to ingest spans" },
      { status: 500 },
    );
  }
}
