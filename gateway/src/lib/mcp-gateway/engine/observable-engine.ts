// ─── Zenic-Agents v3 — Observable Gateway Engine ────────────────────
// Phase 2: Decorator pattern — wraps GatewayEngine with tracing + metrics
//
// Design: Decorator Pattern — adds observability without modifying the
// core GatewayEngine. Each pipeline step becomes a traced span,
// and metrics are recorded after execution completes.
//
// Flow:
//   Request → ObservableGateway.execute()
//     → Start Trace + Root Span
//     → GatewayEngine.execute() (original pipeline)
//       → For each pipeline step: create child span
//     → Complete Trace + Root Span
//     → Record metrics
//     → Return response

import type { GatewayRequest, GatewayResponse } from "../engine/types";
import type { GatewayEngine } from "../engine/gateway-engine";
import { getTraceCollector } from "@/lib/observability/tracing/trace-collector";
import { SpanBuilder, type ActiveSpanHandle } from "@/lib/observability/tracing/span-builder";
import type { SpanRecord } from "@/lib/observability/types/tracing";
import { SPAN_PREFIXES, METRIC_NAMES } from "@/lib/observability/types";
import { recordMetricPoint } from "@/lib/observability/metrics/metrics-collector";

/**
 * ObservableGatewayEngine — decorates GatewayEngine with full tracing.
 *
 * Every call to execute() creates a W3C trace with spans for each
 * pipeline step, and records business/security metrics.
 *
 * Non-invasive: the original GatewayEngine is unchanged.
 * Can be disabled by not using this wrapper.
 */
export class ObservableGatewayEngine {
  private readonly engine: GatewayEngine;
  private readonly enabled: boolean;

  constructor(engine: GatewayEngine, options?: { enabled?: boolean }) {
    this.engine = engine;
    this.enabled = options?.enabled ?? true;
  }

  /**
   * Execute a gateway request with full observability.
   * Delegates to the wrapped GatewayEngine and adds tracing/metrics.
   */
  async execute(request: GatewayRequest): Promise<GatewayResponse> {
    if (!this.enabled) {
      return this.engine.execute(request);
    }

    const collector = getTraceCollector();
    const completedSpans: SpanRecord[] = [];

    // ─── Start Trace ───────────────────────────────────────
    let traceId: string;
    let rootSpan: ActiveSpanHandle;

    try {
      const traceResult = await collector.startTrace({
        sessionId: request.toolCall._meta?.sessionId,
        decisionId: request.toolCall._meta?.decisionId,
        tenantId: request.auth.tenantId,
        attributes: {
          toolName: request.toolCall.name,
          requestId: request.requestId,
          authenticated: request.auth.authenticated,
        },
      });
      traceId = traceResult.traceId;
      rootSpan = traceResult.rootSpan;
    } catch {
      // Tracing unavailable — fall back to non-observable execution
      return this.engine.execute(request);
    }

    // ─── Execute Pipeline with Span Tracking ───────────────
    let response: GatewayResponse;
    try {
      response = await this.engine.execute(request);

      // Create child spans for each pipeline step
      for (const step of response.pipeline) {
        const spanName = mapStepToSpanName(step.name);
        const childSpan = SpanBuilder
          .create(traceId, spanName)
          .withParent(rootSpan.spanId)
          .withResource("tool", request.toolCall.name)
          .withAction(step.name)
          .withAttribute("step.passed", step.passed)
          .withAttribute("step.duration", step.duration)
          .withAttribute("step.reason", step.reason ?? "")
          .start();

        const completedSpan = childSpan.complete({
          status: step.passed ? "ok" : "error",
          statusMessage: step.passed ? undefined : step.reason,
          outcome: step.passed ? "success" : "denied",
          attributes: step.details,
        });

        completedSpans.push(completedSpan);
      }

      // Complete root span
      const finalSpan = rootSpan.complete({
        status: response.verdict === "deny" ? "error" : "ok",
        statusMessage: response.verdict === "deny" ? response.reason : undefined,
        outcome: response.verdict === "allow" ? "success" : response.verdict === "deny" ? "denied" : "failure",
        attributes: {
          verdict: response.verdict,
          executionId: response.executionId,
          totalDuration: response.duration,
          pipelineSteps: response.pipeline.length,
        },
      });
      completedSpans.push(finalSpan);

      // Complete trace
      await collector.completeTrace(traceId, {
        status: response.verdict === "deny" ? "error" : "ok",
        verdict: response.verdict,
        attributes: {
          executionId: response.executionId,
          totalDuration: response.duration,
        },
      });
    } catch (error) {
      // Complete trace with error
      const errorSpan = rootSpan.complete({
        status: "error",
        statusMessage: error instanceof Error ? error.message : "Unknown error",
        outcome: "error",
      });
      completedSpans.push(errorSpan);

      await collector.completeTrace(traceId, {
        status: "error",
        verdict: "deny",
        attributes: { error: error instanceof Error ? error.message : "Unknown error" },
      });

      throw error;
    }

    // ─── Ingest Spans (async, non-blocking) ────────────────
    collector.ingestSpanBatch(completedSpans).catch((e) => {
      console.warn("[Observability] Span ingestion failed:", e instanceof Error ? e.message : String(e));
    });

    // ─── Record Metrics (async, non-blocking) ──────────────
    this.recordMetricsAsync(response);

    // Add trace ID to response pipeline metadata
    return {
      ...response,
      pipeline: response.pipeline.map((step) => ({
        ...step,
        details: { ...step.details, traceId },
      })),
    };
  }

  /**
   * Get the underlying engine (for direct access if needed).
   */
  getInner(): GatewayEngine {
    return this.engine;
  }

  // ─── Private Helpers ──────────────────────────────────────

  private recordMetricsAsync(response: GatewayResponse): void {
    // Fire-and-forget metric recording
    const now = new Date();

    // Gateway latency
    recordMetricPoint({
      name: METRIC_NAMES.GATEWAY_LATENCY,
      value: response.duration,
      timestamp: now,
      labels: { verdict: response.verdict },
    }).catch(() => {});

    // Verdict counts
    const metricName = response.verdict === "deny"
      ? METRIC_NAMES.DENY_RATE
      : response.verdict === "conditional"
        ? METRIC_NAMES.APPROVAL_RATE
        : METRIC_NAMES.EXECUTION_THROUGHPUT;

    recordMetricPoint({
      name: metricName,
      value: 1,
      timestamp: now,
      labels: { verdict: response.verdict },
    }).catch(() => {});

    // Pipeline step durations
    for (const step of response.pipeline) {
      if (step.name === "tool_execution") {
        recordMetricPoint({
          name: METRIC_NAMES.TOOL_EXECUTION_DURATION,
          value: step.duration,
          timestamp: now,
          labels: { step: step.name, passed: String(step.passed) },
        }).catch(() => {});
      }

      // Rate limit hits
      if (step.name === "rate_limit" && !step.passed) {
        recordMetricPoint({
          name: METRIC_NAMES.RATE_LIMIT_HITS,
          value: 1,
          timestamp: now,
          labels: { step: step.name },
        }).catch(() => {});
      }

      // Error tracking
      if (!step.passed) {
        recordMetricPoint({
          name: METRIC_NAMES.ERROR_RATE,
          value: 1,
          timestamp: now,
          labels: { step: step.name, reason: step.reason ?? "unknown" },
        }).catch(() => {});
      }
    }
  }
}

// ─── Step Name Mapper ───────────────────────────────────────────────

/** Map pipeline step names to observability span names */
function mapStepToSpanName(stepName: string): string {
  const mapping: Record<string, string> = {
    tool_resolution: SPAN_PREFIXES.TOOL_RESOLUTION,
    auth_check: SPAN_PREFIXES.AUTH_CHECK,
    rate_limit: SPAN_PREFIXES.RATE_LIMIT,
    rbac_check: SPAN_PREFIXES.RBAC_CHECK,
    risk_policy: SPAN_PREFIXES.RISK_POLICY,
    tool_execution: SPAN_PREFIXES.TOOL_EXECUTE,
    merkle_audit: SPAN_PREFIXES.MERKLE_AUDIT,
  };
  return mapping[stepName] ?? `gateway.${stepName}`;
}
