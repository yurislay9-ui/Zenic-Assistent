// ─── Zenic-Agents v3 — OpenTelemetry Exporter ────────────────────────
// Phase 2: OTLP JSON format export for Grafana/Jaeger integration
//
// Converts internal Trace+Span records into OTLP-compatible format.
// Strategy Pattern — one of multiple export strategies.

import { db } from "@/lib/db";
import type { OtelSpan, OtelResourceSpan, OtelExportPayload, ExportQueryParams } from "../types/export";
import type { TraceRecord, SpanRecord } from "../types/tracing";
import { OBSERVABILITY_SERVICE } from "../types";

// ─── OTLP Export ────────────────────────────────────────────────────

/**
 * Export traces in OpenTelemetry Protocol (OTLP) JSON format.
 * Compatible with Grafana Tempo, Jaeger, and any OTLP collector.
 */
export async function exportOtel(params: ExportQueryParams): Promise<OtelExportPayload> {
  const traces = await fetchTracesForExport(params);
  const spans = await fetchSpansForTraces(traces.map((t) => t.traceId));

  const otelSpans: OtelSpan[] = spans.map(convertSpanToOtel);

  const resourceSpan: OtelResourceSpan = {
    resource: {
      attributes: [
        { key: "service.name", value: { stringValue: OBSERVABILITY_SERVICE } },
        { key: "service.version", value: { stringValue: "3.0.0" } },
        { key: "service.namespace", value: { stringValue: "zenic-agents" } },
      ],
    },
    scopeSpans: [
      {
        scope: {
          name: "zenic-gateway",
          version: "3.0.0",
        },
        spans: otelSpans,
      },
    ],
  };

  return {
    resourceSpans: [resourceSpan],
  };
}

// ─── Span Conversion ────────────────────────────────────────────────

/**
 * Convert internal SpanRecord to OTLP Span format.
 * Handles W3C trace context, attributes, events, and links.
 */
function convertSpanToOtel(span: SpanRecord): OtelSpan {
  const otelSpan: OtelSpan = {
    traceId: span.traceId,
    spanId: span.spanId,
    parentSpanId: span.parentSpanId ?? "",
    name: span.name,
    kind: mapSpanKind(span.kind),
    startTimeUnixNano: dateToNano(span.startTime),
    endTimeUnixNano: span.endTime ? dateToNano(span.endTime) : "0",
    status: {
      code: span.status === "ok" ? 1 : span.status === "error" ? 2 : 0,
      ...(span.statusMessage ? { message: span.statusMessage } : {}),
    },
  };

  // Attributes
  const attrs: OtelSpan["attributes"] = [];
  if (span.resource) attrs.push({ key: "zenic.resource", value: { stringValue: span.resource } });
  if (span.resourceId) attrs.push({ key: "zenic.resource_id", value: { stringValue: span.resourceId } });
  if (span.action) attrs.push({ key: "zenic.action", value: { stringValue: span.action } });
  if (span.outcome) attrs.push({ key: "zenic.outcome", value: { stringValue: span.outcome } });
  if (span.duration != null) attrs.push({ key: "zenic.duration_ms", value: { intValue: String(span.duration) } });

  for (const [key, value] of Object.entries(span.attributes)) {
    if (typeof value === "string") {
      attrs.push({ key: `zenic.attr.${key}`, value: { stringValue: value } });
    } else if (typeof value === "number") {
      attrs.push({ key: `zenic.attr.${key}`, value: { doubleValue: value } });
    } else if (typeof value === "boolean") {
      attrs.push({ key: `zenic.attr.${key}`, value: { stringValue: String(value) } });
    }
  }

  if (attrs.length > 0) otelSpan.attributes = attrs;

  // Events
  if (span.events.length > 0) {
    otelSpan.events = span.events.map((evt) => ({
      timeUnixNano: isoToNano(evt.timestamp),
      name: evt.name,
      attributes: evt.attributes
        ? Object.entries(evt.attributes).map(([k, v]) => ({
            key: k,
            value: { stringValue: String(v) },
          }))
        : undefined,
    }));
  }

  // Links
  if (span.links.length > 0) {
    otelSpan.links = span.links.map((link) => ({
      traceId: link.traceId,
      spanId: link.spanId,
      attributes: link.attributes
        ? Object.entries(link.attributes).map(([k, v]) => ({
            key: k,
            value: { stringValue: String(v) },
          }))
        : undefined,
    }));
  }

  return otelSpan;
}

// ─── Data Fetching ──────────────────────────────────────────────────

async function fetchTracesForExport(params: ExportQueryParams): Promise<TraceRecord[]> {
  const where: Record<string, unknown> = {};

  if (params.traceIds && params.traceIds.length > 0) {
    where.traceId = { in: params.traceIds };
  }
  if (params.sessionId) {
    where.sessionId = params.sessionId;
  }
  if (params.startDate || params.endDate) {
    const createdAt: Record<string, Date> = {};
    if (params.startDate) createdAt.gte = new Date(params.startDate);
    if (params.endDate) createdAt.lte = new Date(params.endDate);
    where.createdAt = createdAt;
  }

  const limit = params.limit ?? 100;

  const rawTraces = await db.trace.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: limit,
  });

  return rawTraces.map(mapTrace);
}

async function fetchSpansForTraces(traceIds: string[]): Promise<SpanRecord[]> {
  if (traceIds.length === 0) return [];

  const rawSpans = await db.span.findMany({
    where: { traceId: { in: traceIds } },
    orderBy: { startTime: "asc" },
  });

  return rawSpans.map(mapSpan);
}

// ─── Mappers ────────────────────────────────────────────────────────

function mapTrace(raw: {
  id: string; traceId: string; sessionId: string | null; decisionId: string | null;
  tenantId: string | null; rootSpanId: string | null; status: string; verdict: string | null;
  duration: number | null; spanCount: number; serviceName: string; attributes: string;
  createdAt: Date; completedAt: Date | null;
}): TraceRecord {
  return {
    id: raw.id, traceId: raw.traceId, sessionId: raw.sessionId,
    decisionId: raw.decisionId, tenantId: raw.tenantId, rootSpanId: raw.rootSpanId,
    status: raw.status as TraceRecord["status"], verdict: raw.verdict, duration: raw.duration,
    spanCount: raw.spanCount, serviceName: raw.serviceName,
    attributes: safeParseJson<Record<string, unknown>>(raw.attributes),
    createdAt: raw.createdAt, completedAt: raw.completedAt,
  };
}

function mapSpan(raw: {
  id: string; spanId: string; traceId: string; parentSpanId: string | null;
  name: string; kind: string; status: string; statusMessage: string | null;
  startTime: Date; endTime: Date | null; duration: number | null; service: string;
  resource: string | null; resourceId: string | null; action: string | null;
  outcome: string | null; attributes: string; events: string; links: string; createdAt: Date;
}): SpanRecord {
  return {
    id: raw.id, spanId: raw.spanId, traceId: raw.traceId, parentSpanId: raw.parentSpanId,
    name: raw.name, kind: raw.kind as SpanRecord["kind"], status: raw.status as SpanRecord["status"],
    statusMessage: raw.statusMessage, startTime: raw.startTime, endTime: raw.endTime,
    duration: raw.duration, service: raw.service, resource: raw.resource, resourceId: raw.resourceId,
    action: raw.action, outcome: raw.outcome,
    attributes: safeParseJson<Record<string, unknown>>(raw.attributes),
    events: safeParseJson<SpanRecord["events"]>(raw.events),
    links: safeParseJson<SpanRecord["links"]>(raw.links),
    createdAt: raw.createdAt,
  };
}

// ─── Utility Functions ──────────────────────────────────────────────

/** Map internal SpanKind to OTLP numeric kind */
function mapSpanKind(kind: string): number {
  const kindMap: Record<string, number> = {
    internal: 1,
    server: 2,
    client: 3,
    producer: 4,
    consumer: 5,
  };
  return kindMap[kind] ?? 1;
}

/** Convert Date to nanoseconds since epoch string */
function dateToNano(date: Date): string {
  return String(date.getTime() * 1_000_000);
}

/** Convert ISO 8601 string to nanoseconds since epoch string */
function isoToNano(iso: string): string {
  return String(new Date(iso).getTime() * 1_000_000);
}

function safeParseJson<T>(json: string): T {
  try { return JSON.parse(json) as T; }
  catch { return {} as T; }
}
