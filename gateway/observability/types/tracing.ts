// ─── Zenic-Agents v3 — Tracing Type System ──────────────────────────
// Phase 2: Distributed tracing types — W3C Trace Context compatible

// ─── Enum-like Constants ────────────────────────────────────────────

/** Trace status */
export const TraceStatus = {
  OK: "ok",
  ERROR: "error",
  TIMEOUT: "timeout",
  PARTIAL: "partial",
} as const;
export type TraceStatus = (typeof TraceStatus)[keyof typeof TraceStatus];

/** Span kinds — OpenTelemetry compatible */
export const SpanKind = {
  INTERNAL: "internal",
  SERVER: "server",
  CLIENT: "client",
  PRODUCER: "producer",
  CONSUMER: "consumer",
} as const;
export type SpanKind = (typeof SpanKind)[keyof typeof SpanKind];

/** Span status */
export const SpanStatus = {
  OK: "ok",
  ERROR: "error",
  TIMEOUT: "timeout",
} as const;
export type SpanStatus = (typeof SpanStatus)[keyof typeof SpanStatus];

// ─── Core Types ─────────────────────────────────────────────────────

/** A span event — an annotation within a span */
export interface SpanEvent {
  /** Event name */
  name: string;
  /** When the event occurred (ISO 8601) */
  timestamp: string;
  /** Event attributes */
  attributes?: Record<string, unknown>;
}

/** A span link — causal reference to another span */
export interface SpanLink {
  /** Linked trace ID */
  traceId: string;
  /** Linked span ID */
  spanId: string;
  /** Link attributes */
  attributes?: Record<string, unknown>;
}

/** A complete trace record — maps to Prisma Trace model */
export interface TraceRecord {
  id: string;
  traceId: string;
  sessionId?: string | null;
  decisionId?: string | null;
  tenantId?: string | null;
  rootSpanId?: string | null;
  status: TraceStatus;
  verdict?: string | null;
  duration?: number | null;
  spanCount: number;
  serviceName: string;
  attributes: Record<string, unknown>;
  createdAt: Date;
  completedAt?: Date | null;
}

/** A single span within a trace — maps to Prisma Span model */
export interface SpanRecord {
  id: string;
  spanId: string;
  traceId: string;
  parentSpanId?: string | null;
  name: string;
  kind: SpanKind;
  status: SpanStatus;
  statusMessage?: string | null;
  startTime: Date;
  endTime?: Date | null;
  duration?: number | null;
  service: string;
  resource?: string | null;
  resourceId?: string | null;
  action?: string | null;
  outcome?: string | null;
  attributes: Record<string, unknown>;
  events: SpanEvent[];
  links: SpanLink[];
  createdAt: Date;
}

/** Trace with all its spans — full view */
export interface TraceWithSpans extends TraceRecord {
  spans: SpanRecord[];
}

// ─── Query Types ────────────────────────────────────────────────────

/** Parameters for querying traces */
export interface TraceQueryParams {
  /** Filter by trace ID */
  traceId?: string;
  /** Filter by session ID */
  sessionId?: string;
  /** Filter by decision ID */
  decisionId?: string;
  /** Filter by tenant */
  tenantId?: string;
  /** Filter by status */
  status?: TraceStatus;
  /** Filter by verdict */
  verdict?: string;
  /** Filter traces created after this date */
  startDate?: string;
  /** Filter traces created before this date */
  endDate?: string;
  /** Minimum duration in ms */
  minDuration?: number;
  /** Maximum duration in ms */
  maxDuration?: number;
  /** Search term in attributes */
  search?: string;
  /** Pagination: page number (1-based) */
  page?: number;
  /** Pagination: items per page */
  pageSize?: number;
  /** Sort field */
  sortBy?: "createdAt" | "duration" | "spanCount";
  /** Sort direction */
  sortOrder?: "asc" | "desc";
}

// ─── Span Builder Types ─────────────────────────────────────────────

/** Parameters for creating a new span */
export interface SpanCreateParams {
  /** W3C trace ID — must already exist in Trace table */
  traceId: string;
  /** Parent span ID for nesting (null = root span) */
  parentSpanId?: string | null;
  /** Span name — use SPAN_PREFIXES constants */
  name: string;
  /** Span kind */
  kind?: SpanKind;
  /** Resource being operated on */
  resource?: string;
  /** Resource identifier */
  resourceId?: string;
  /** Action being performed */
  action?: string;
  /** Span attributes */
  attributes?: Record<string, unknown>;
}

/** Parameters for completing a span */
export interface SpanCompleteParams {
  /** Span ID to complete */
  spanId: string;
  /** Final status */
  status?: SpanStatus;
  /** Error message if status is error */
  statusMessage?: string;
  /** Outcome of the operation */
  outcome?: "success" | "failure" | "denied" | "error";
  /** Additional attributes to merge */
  attributes?: Record<string, unknown>;
  /** Events that occurred during the span */
  events?: SpanEvent[];
  /** Links to other spans */
  links?: SpanLink[];
}
