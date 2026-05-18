// ─── Zenic-Agents v3 — Trace Collector Formatters & Helpers ────────
// Mapper functions, ID generators, and JSON helpers for trace/span records.

import { randomUUID } from "crypto";
import type { TraceRecord, SpanRecord, TraceStatus } from "../../types/tracing";

// ─── Mapper Functions ───────────────────────────────────────────────

export function mapTraceRecord(raw: {
  id: string;
  traceId: string;
  sessionId: string | null;
  decisionId: string | null;
  tenantId: string | null;
  rootSpanId: string | null;
  status: string;
  verdict: string | null;
  duration: number | null;
  spanCount: number;
  serviceName: string;
  attributes: string;
  createdAt: Date;
  completedAt: Date | null;
}): TraceRecord {
  return {
    id: raw.id,
    traceId: raw.traceId,
    sessionId: raw.sessionId,
    decisionId: raw.decisionId,
    tenantId: raw.tenantId,
    rootSpanId: raw.rootSpanId,
    status: raw.status as TraceStatus,
    verdict: raw.verdict,
    duration: raw.duration,
    spanCount: raw.spanCount,
    serviceName: raw.serviceName,
    attributes: safeParseJson<Record<string, unknown>>(raw.attributes),
    createdAt: raw.createdAt,
    completedAt: raw.completedAt,
  };
}

export function mapSpanRecord(raw: {
  id: string;
  spanId: string;
  traceId: string;
  parentSpanId: string | null;
  name: string;
  kind: string;
  status: string;
  statusMessage: string | null;
  startTime: Date;
  endTime: Date | null;
  duration: number | null;
  service: string;
  resource: string | null;
  resourceId: string | null;
  action: string | null;
  outcome: string | null;
  attributes: string;
  events: string;
  links: string;
  createdAt: Date;
}): SpanRecord {
  return {
    id: raw.id,
    spanId: raw.spanId,
    traceId: raw.traceId,
    parentSpanId: raw.parentSpanId,
    name: raw.name,
    kind: raw.kind as SpanRecord["kind"],
    status: raw.status as SpanRecord["status"],
    statusMessage: raw.statusMessage,
    startTime: raw.startTime,
    endTime: raw.endTime,
    duration: raw.duration,
    service: raw.service,
    resource: raw.resource,
    resourceId: raw.resourceId,
    action: raw.action,
    outcome: raw.outcome,
    attributes: safeParseJson<Record<string, unknown>>(raw.attributes),
    events: safeParseJson<SpanRecord["events"]>(raw.events),
    links: safeParseJson<SpanRecord["links"]>(raw.links),
    createdAt: raw.createdAt,
  };
}

// ─── Helpers ────────────────────────────────────────────────────────

/** Generate a W3C-compatible trace ID (32 hex chars) */
export function generateTraceId(): string {
  return randomUUID().replace(/-/g, "") + randomUUID().replace(/-/g, "").slice(0, 16);
}

/** Safely parse JSON with a fallback */
export function safeParseJson<T>(json: string): T {
  try {
    return JSON.parse(json) as T;
  } catch {
    return {} as T;
  }
}
