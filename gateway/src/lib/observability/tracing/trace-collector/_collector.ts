// ─── Zenic-Agents v3 — Trace Collector Service ──────────────────────
// Phase 2: Trace ingestion, persistence, and querying
// Repository Pattern — all DB access goes through this service.

import { db } from "@/lib/db";
import type { TraceRecord, SpanRecord, TraceWithSpans, TraceQueryParams, TraceStatus } from "../../types/tracing";
import { OBSERVABILITY_SERVICE } from "../../types";
import { SpanBuilder, type ActiveSpanHandle } from "../span-builder";
import { mapTraceRecord, mapSpanRecord, generateTraceId, safeParseJson } from "./_formatter";

// ─── Trace Creation ─────────────────────────────────────────────────

/** Parameters for creating a new trace */
export interface TraceCreateParams {
  /** Optional session ID for business correlation */
  sessionId?: string;
  /** Optional decision ID for verdict correlation */
  decisionId?: string;
  /** Optional tenant ID for isolation */
  tenantId?: string;
  /** Trace attributes */
  attributes?: Record<string, unknown>;
}

// ─── Trace Collector ────────────────────────────────────────────────

/**
 * Central service for trace lifecycle management.
 * Handles creation, span ingestion, completion, and querying.
 *
 * Design: Repository Pattern — encapsulates all Prisma operations
 * for the Trace and Span models.
 */
export class TraceCollector {
  // ─── Trace Lifecycle ─────────────────────────────────────────────

  /**
   * Start a new trace — creates the trace record and root span.
   * Returns the trace ID and root span handle.
   */
  async startTrace(params: TraceCreateParams = {}): Promise<{
    traceId: string;
    rootSpan: ActiveSpanHandle;
  }> {
    const traceId = generateTraceId();

    // Create trace record in DB
    await db.trace.create({
      data: {
        traceId,
        sessionId: params.sessionId ?? null,
        decisionId: params.decisionId ?? null,
        tenantId: params.tenantId ?? null,
        status: "ok",
        serviceName: OBSERVABILITY_SERVICE,
        attributes: JSON.stringify(params.attributes ?? {}),
        spanCount: 0,
      },
    });

    // Create root span builder
    const rootSpan = SpanBuilder
      .create(traceId, "gateway.request")
      .withKind("server")
      .withAttribute("session.id", params.sessionId)
      .withAttribute("decision.id", params.decisionId)
      .withAttribute("tenant.id", params.tenantId)
      .start();

    // Update trace with root span ID
    await db.trace.update({
      where: { traceId },
      data: { rootSpanId: rootSpan.spanId },
    });

    return { traceId, rootSpan };
  }

  /**
   * Complete a trace — sets final status, verdict, duration.
   * Also completes the root span if still active.
   */
  async completeTrace(
    traceId: string,
    params: {
      status?: TraceStatus;
      verdict?: string;
      attributes?: Record<string, unknown>;
    } = {},
  ): Promise<TraceRecord | null> {
    const trace = await db.trace.findUnique({ where: { traceId } });
    if (!trace) return null;

    const existingAttrs = safeParseJson<Record<string, unknown>>(trace.attributes);
    const mergedAttrs = { ...existingAttrs, ...(params.attributes ?? {}) };

    const updated = await db.trace.update({
      where: { traceId },
      data: {
        status: params.status ?? "ok",
        verdict: params.verdict ?? trace.verdict,
        completedAt: new Date(),
        attributes: JSON.stringify(mergedAttrs),
      },
    });

    return mapTraceRecord(updated);
  }

  // ─── Span Ingestion ──────────────────────────────────────────────

  /**
   * Persist a completed span to the database.
   * Called after ActiveSpanHandle.complete() returns a SpanRecord.
   */
  async ingestSpan(span: SpanRecord): Promise<void> {
    const exists = await db.trace.findUnique({ where: { traceId: span.traceId } });
    if (!exists) {
      // Auto-create trace if it doesn't exist (defensive)
      await db.trace.create({
        data: {
          traceId: span.traceId,
          status: "ok",
          serviceName: span.service,
          attributes: "{}",
          spanCount: 0,
        },
      });
    }

    await db.span.create({
      data: {
        spanId: span.spanId,
        traceId: span.traceId,
        parentSpanId: span.parentSpanId,
        name: span.name,
        kind: span.kind,
        status: span.status,
        statusMessage: span.statusMessage,
        startTime: span.startTime,
        endTime: span.endTime,
        duration: span.duration,
        service: span.service,
        resource: span.resource,
        resourceId: span.resourceId,
        action: span.action,
        outcome: span.outcome,
        attributes: JSON.stringify(span.attributes),
        events: JSON.stringify(span.events),
        links: JSON.stringify(span.links),
      },
    });

    // Increment span count on trace
    await db.trace.update({
      where: { traceId: span.traceId },
      data: {
        spanCount: { increment: 1 },
        // Update trace status if span has error
        ...(span.status === "error" ? { status: "error" } : {}),
        // Update trace duration if this is the latest span
        ...(span.duration != null ? { duration: Math.max(span.duration, exists?.duration ?? 0) } : {}),
      },
    });
  }

  /**
   * Ingest multiple spans in batch.
   * More efficient than individual ingestSpan calls.
   */
  async ingestSpanBatch(spans: SpanRecord[]): Promise<void> {
    if (spans.length === 0) return;

    // Group by traceId for efficient updates
    const byTrace = new Map<string, SpanRecord[]>();
    for (const span of spans) {
      const existing = byTrace.get(span.traceId) ?? [];
      existing.push(span);
      byTrace.set(span.traceId, existing);
    }

    // Ensure all traces exist
    for (const [traceId, traceSpans] of byTrace) {
      const exists = await db.trace.findUnique({ where: { traceId } });
      if (!exists) {
        await db.trace.create({
          data: {
            traceId,
            status: "ok",
            serviceName: traceSpans[0]?.service ?? OBSERVABILITY_SERVICE,
            attributes: "{}",
            spanCount: 0,
          },
        });
      }
    }

    // Batch insert spans
    await db.span.createMany({
      data: spans.map((span) => ({
        spanId: span.spanId,
        traceId: span.traceId,
        parentSpanId: span.parentSpanId,
        name: span.name,
        kind: span.kind,
        status: span.status,
        statusMessage: span.statusMessage,
        startTime: span.startTime,
        endTime: span.endTime,
        duration: span.duration,
        service: span.service,
        resource: span.resource,
        resourceId: span.resourceId,
        action: span.action,
        outcome: span.outcome,
        attributes: JSON.stringify(span.attributes),
        events: JSON.stringify(span.events),
        links: JSON.stringify(span.links),
      })),
    });

    // Update trace counts
    for (const [traceId, traceSpans] of byTrace) {
      const hasError = traceSpans.some((s) => s.status === "error");
      const maxDuration = Math.max(...traceSpans.map((s) => s.duration ?? 0));

      await db.trace.update({
        where: { traceId },
        data: {
          spanCount: { increment: traceSpans.length },
          ...(hasError ? { status: "error" } : {}),
          ...(maxDuration > 0 ? { duration: maxDuration } : {}),
        },
      });
    }
  }

  // ─── Query Operations ────────────────────────────────────────────

  /** Get a single trace by trace ID, with all its spans */
  async getTrace(traceId: string): Promise<TraceWithSpans | null> {
    const trace = await db.trace.findUnique({
      where: { traceId },
      include: { spans: { orderBy: { startTime: "asc" } } },
    });

    if (!trace) return null;

    return {
      ...mapTraceRecord(trace),
      spans: trace.spans.map(mapSpanRecord),
    };
  }

  /** Query traces with filters and pagination */
  async queryTraces(params: TraceQueryParams = {}): Promise<{
    traces: TraceRecord[];
    total: number;
    page: number;
    pageSize: number;
    totalPages: number;
  }> {
    const {
      traceId, sessionId, decisionId, tenantId, status, verdict,
      startDate, endDate, minDuration, maxDuration,
      page = 1, pageSize = 20, sortBy = "createdAt", sortOrder = "desc",
    } = params;

    const where: Record<string, unknown> = {};

    if (traceId) where.traceId = { contains: traceId };
    if (sessionId) where.sessionId = sessionId;
    if (decisionId) where.decisionId = decisionId;
    if (tenantId) where.tenantId = tenantId;
    if (status) where.status = status;
    if (verdict) where.verdict = verdict;

    if (startDate || endDate) {
      const createdAt: Record<string, Date> = {};
      if (startDate) createdAt.gte = new Date(startDate);
      if (endDate) createdAt.lte = new Date(endDate);
      where.createdAt = createdAt;
    }

    if (minDuration != null || maxDuration != null) {
      const duration: Record<string, number> = {};
      if (minDuration != null) duration.gte = minDuration;
      if (maxDuration != null) duration.lte = maxDuration;
      where.duration = duration;
    }

    const [traces, total] = await Promise.all([
      db.trace.findMany({
        where,
        orderBy: { [sortBy]: sortOrder },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.trace.count({ where }),
    ]);

    return {
      traces: traces.map(mapTraceRecord),
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    };
  }

  /** Get recent traces — simple shortcut for dashboards */
  async getRecentTraces(limit = 20): Promise<TraceWithSpans[]> {
    const traces = await db.trace.findMany({
      orderBy: { createdAt: "desc" },
      take: limit,
      include: { spans: { orderBy: { startTime: "asc" } } },
    });

    return traces.map((t) => ({
      ...mapTraceRecord(t),
      spans: t.spans.map(mapSpanRecord),
    }));
  }

  /** Get trace counts by status */
  async getTraceStatusCounts(since?: Date): Promise<Record<TraceStatus, number>> {
    const where = since ? { createdAt: { gte: since } } : {};

    const results = await db.trace.groupBy({
      by: ["status"],
      where,
      _count: { id: true },
    });

    const counts: Record<string, number> = { ok: 0, error: 0, timeout: 0, partial: 0 };
    for (const r of results) {
      counts[r.status] = r._count.id;
    }

    return counts as Record<TraceStatus, number>;
  }

  /** Get trace counts by verdict */
  async getTraceVerdictCounts(since?: Date): Promise<Record<string, number>> {
    const where = since ? { createdAt: { gte: since } } : {};

    const results = await db.trace.groupBy({
      by: ["verdict"],
      where,
      _count: { id: true },
    });

    const counts: Record<string, number> = { allow: 0, deny: 0, conditional: 0 };
    for (const r of results) {
      if (r.verdict) counts[r.verdict] = r._count.id;
    }

    return counts;
  }

  /**
   * Convenience: create a span builder pre-wired to a trace.
   * The returned builder must be .start()-ed and .complete()-d,
   * then the completed SpanRecord must be passed to ingestSpan().
   */
  createSpanBuilder(traceId: string, name: string): SpanBuilder {
    return SpanBuilder.create(traceId, name);
  }
}

// ─── Singleton Instance ─────────────────────────────────────────────

let instance: TraceCollector | null = null;

/** Get the singleton TraceCollector instance */
export function getTraceCollector(): TraceCollector {
  if (!instance) {
    instance = new TraceCollector();
  }
  return instance;
}

/** Reset the singleton (for testing) */
export function resetTraceCollector(): void {
  instance = null;
}
