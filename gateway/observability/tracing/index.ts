// ─── Zenic-Agents v3 — Tracing Barrel Export ────────────────────────
// Public API for the tracing subsystem

export { SpanBuilder, ActiveSpanHandle, getActiveSpan, getActiveSpanIds, getActiveSpanCount } from "./span-builder";
export { TraceCollector, getTraceCollector, resetTraceCollector } from "./trace-collector";
export type { TraceCreateParams } from "./trace-collector";
