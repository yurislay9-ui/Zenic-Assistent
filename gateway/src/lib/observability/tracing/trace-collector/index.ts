// ─── Zenic-Agents v3 — Trace Collector (barrel) ────────────────────

export {
  TraceCollector,
  getTraceCollector,
  resetTraceCollector,
  type TraceCreateParams,
} from "./_collector";

export {
  mapTraceRecord,
  mapSpanRecord,
  generateTraceId,
  safeParseJson,
} from "./_formatter";
