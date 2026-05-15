// ─── Zenic-Agents v3 — Span Builder ─────────────────────────────────
// Phase 2: Builder pattern for constructing spans with fluent API
//
// Usage:
//   const span = SpanBuilder.create(traceId, "gateway.auth_check")
//     .withKind("internal")
//     .withResource("tool", "db_query")
//     .withAction("check")
//     .withAttribute("auth.method", "api_key")
//     .start();
//   // ... do work ...
//   span.complete({ status: "ok", outcome: "success" });

import { randomUUID } from "crypto";
import type { SpanKind, SpanStatus, SpanRecord, SpanEvent, SpanLink, SpanCreateParams, SpanCompleteParams } from "../types/tracing";
import { OBSERVABILITY_SERVICE } from "../types";

// ─── Active Span Tracking ───────────────────────────────────────────

/** Tracks in-flight spans for the current process */
const activeSpans = new Map<string, InFlightSpan>();

/** An in-flight span — started but not yet completed */
interface InFlightSpan {
  spanId: string;
  traceId: string;
  parentSpanId: string | null;
  name: string;
  kind: SpanKind;
  startTime: Date;
  service: string;
  resource: string | null;
  resourceId: string | null;
  action: string | null;
  attributes: Record<string, unknown>;
  events: SpanEvent[];
  links: SpanLink[];
}

// ─── Span Builder ───────────────────────────────────────────────────

/**
 * Fluent builder for constructing and tracking spans.
 * Implements the Builder pattern for clean, type-safe span creation.
 */
export class SpanBuilder {
  private params: SpanCreateParams;
  private spanId: string;
  private service: string;
  private extraAttributes: Record<string, unknown>;
  private spanEvents: SpanEvent[];
  private spanLinks: SpanLink[];

  private constructor(traceId: string, name: string) {
    this.spanId = generateSpanId();
    this.params = { traceId, name };
    this.service = OBSERVABILITY_SERVICE;
    this.extraAttributes = {};
    this.spanEvents = [];
    this.spanLinks = [];
  }

  /** Create a new span builder for the given trace and span name */
  static create(traceId: string, name: string): SpanBuilder {
    return new SpanBuilder(traceId, name);
  }

  /** Set the span kind */
  withKind(kind: SpanKind): this {
    this.params.kind = kind;
    return this;
  }

  /** Set the parent span ID for nesting */
  withParent(parentSpanId: string): this {
    this.params.parentSpanId = parentSpanId;
    return this;
  }

  /** Set the resource being operated on */
  withResource(resource: string, resourceId?: string): this {
    this.params.resource = resource;
    this.params.resourceId = resourceId;
    return this;
  }

  /** Set the action being performed */
  withAction(action: string): this {
    this.params.action = action;
    return this;
  }

  /** Add a single attribute */
  withAttribute(key: string, value: unknown): this {
    this.extraAttributes[key] = value;
    return this;
  }

  /** Add multiple attributes */
  withAttributes(attrs: Record<string, unknown>): this {
    Object.assign(this.extraAttributes, attrs);
    return this;
  }

  /** Add an event to the span */
  withEvent(name: string, attributes?: Record<string, unknown>): this {
    this.spanEvents.push({
      name,
      timestamp: new Date().toISOString(),
      attributes,
    });
    return this;
  }

  /** Add a link to another span */
  withLink(traceId: string, spanId: string, attributes?: Record<string, unknown>): this {
    this.spanLinks.push({ traceId, spanId, attributes });
    return this;
  }

  /** Set the service name */
  withService(service: string): this {
    this.service = service;
    return this;
  }

  /**
   * Start the span — registers it in the active spans tracker.
   * Returns a handle that can be used to complete the span.
   */
  start(): ActiveSpanHandle {
    const now = new Date();
    const inFlight: InFlightSpan = {
      spanId: this.spanId,
      traceId: this.params.traceId,
      parentSpanId: this.params.parentSpanId ?? null,
      name: this.params.name,
      kind: this.params.kind ?? "internal",
      startTime: now,
      service: this.service,
      resource: this.params.resource ?? null,
      resourceId: this.params.resourceId ?? null,
      action: this.params.action ?? null,
      attributes: { ...this.params.attributes, ...this.extraAttributes },
      events: [...this.spanEvents],
      links: [...this.spanLinks],
    };

    activeSpans.set(this.spanId, inFlight);

    return new ActiveSpanHandle(inFlight);
  }

  /** Get the span ID that will be assigned (before start) */
  getSpanId(): string {
    return this.spanId;
  }
}

// ─── Active Span Handle ─────────────────────────────────────────────

/**
 * Handle to an in-flight span — allows adding events and completing.
 * Returned by SpanBuilder.start().
 */
export class ActiveSpanHandle {
  private readonly inFlight: InFlightSpan;
  private completed = false;

  constructor(inFlight: InFlightSpan) {
    this.inFlight = inFlight;
  }

  /** Get the span ID */
  get spanId(): string {
    return this.inFlight.spanId;
  }

  /** Get the trace ID */
  get traceId(): string {
    return this.inFlight.traceId;
  }

  /** Get the parent span ID */
  get parentSpanId(): string | null {
    return this.inFlight.parentSpanId;
  }

  /** Get the span name */
  get name(): string {
    return this.inFlight.name;
  }

  /** Add an event to the in-flight span */
  addEvent(name: string, attributes?: Record<string, unknown>): this {
    if (this.completed) return this;
    this.inFlight.events.push({
      name,
      timestamp: new Date().toISOString(),
      attributes,
    });
    return this;
  }

  /** Add an attribute to the in-flight span */
  addAttribute(key: string, value: unknown): this {
    if (this.completed) return this;
    this.inFlight.attributes[key] = value;
    return this;
  }

  /**
   * Complete the span — removes it from active tracking and returns
   * the complete SpanRecord ready for persistence.
   */
  complete(params: SpanCompleteParams = {}): SpanRecord {
    if (this.completed) {
      throw new Error(`Span ${this.inFlight.spanId} already completed`);
    }

    this.completed = true;
    activeSpans.delete(this.inFlight.spanId);

    const endTime = new Date();
    const duration = endTime.getTime() - this.inFlight.startTime.getTime();
    const status: SpanStatus = params.status ?? "ok";

    // Merge any additional attributes
    const mergedAttributes = {
      ...this.inFlight.attributes,
      ...(params.attributes ?? {}),
    };

    // Merge events
    const mergedEvents = [
      ...this.inFlight.events,
      ...(params.events ?? []),
    ];

    // Merge links
    const mergedLinks = [
      ...this.inFlight.links,
      ...(params.links ?? []),
    ];

    return {
      id: "", // Will be set by DB on insert
      spanId: this.inFlight.spanId,
      traceId: this.inFlight.traceId,
      parentSpanId: this.inFlight.parentSpanId,
      name: this.inFlight.name,
      kind: this.inFlight.kind,
      status,
      statusMessage: params.statusMessage ?? null,
      startTime: this.inFlight.startTime,
      endTime,
      duration,
      service: this.inFlight.service,
      resource: this.inFlight.resource,
      resourceId: this.inFlight.resourceId,
      action: this.inFlight.action,
      outcome: params.outcome ?? null,
      attributes: mergedAttributes,
      events: mergedEvents,
      links: mergedLinks,
      createdAt: new Date(),
    };
  }
}

// ─── Utility Functions ──────────────────────────────────────────────

/** Generate a W3C-compatible span ID (16 hex chars) */
function generateSpanId(): string {
  return randomUUID().replace(/-/g, "").slice(0, 16);
}

/** Get an active span by ID (if still in-flight) */
export function getActiveSpan(spanId: string): InFlightSpan | undefined {
  return activeSpans.get(spanId);
}

/** Get all currently active span IDs */
export function getActiveSpanIds(): string[] {
  return Array.from(activeSpans.keys());
}

/** Count of currently active spans */
export function getActiveSpanCount(): number {
  return activeSpans.size;
}
