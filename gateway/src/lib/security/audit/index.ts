// ─── Zenic-Agents Gateway — Structured Audit Logging Module ──────────
// Provides centralized, structured audit logging for all critical gateway
// operations. Events are always written to the console as structured JSON
// and persisted to the Prisma AuditLog table when the database is available.
// If the database write fails, the console log is still emitted (fail-open).

import { db } from '../../db';

// ─── Type Definitions ───────────────────────────────────────────────

/**
 * Event types categorised by the domain of the gateway operation.
 *
 * - `auth`           — Authentication & authorization events (login, token refresh, etc.)
 * - `data_access`    — Read/write operations on protected resources
 * - `admin_action`   — Administrative changes (role assignment, config update, etc.)
 * - `security_event` — Anomalous or policy-violating events (brute-force, rate-limit breach)
 * - `hitl_decision`  — Human-in-the-loop approval / rejection / escalation
 * - `subscription`   — Tenant subscription plan changes
 * - `payment`        — Billing and payment operations
 */
export type AuditEventType =
  | 'auth'
  | 'data_access'
  | 'admin_action'
  | 'security_event'
  | 'hitl_decision'
  | 'subscription'
  | 'payment';

/**
 * The outcome of the audited operation.
 *
 * - `success` — The operation completed as intended
 * - `failure` — The operation was attempted but failed (e.g. wrong password)
 * - `denied`  — The operation was explicitly denied by policy
 */
export type AuditResult = 'success' | 'failure' | 'denied';

/**
 * Severity level for audit events, controlling log level and alerting.
 *
 * - `low`      — Routine operations (e.g. successful login)
 * - `medium`   — Noteworthy but non-threatening (e.g. password change)
 * - `high`     — Potentially harmful (e.g. role escalation, bulk delete)
 * - `critical` — Immediate investigation required (e.g. breach, data exfiltration)
 */
export type AuditSeverity = 'low' | 'medium' | 'high' | 'critical';

/**
 * Structured representation of an auditable event.
 *
 * All fields except `timestamp`, `eventType`, `action`, `result`, and
 * `severity` are optional to accommodate the varied shape of different
 * event categories. Convenience methods on {@link AuditLogger} fill in
 * sensible defaults for each category.
 */
export interface AuditEvent {
  /** ISO 8601 timestamp of when the event occurred */
  timestamp: string;

  /** High-level category of the event */
  eventType: AuditEventType;

  /** ID of the user or service principal that triggered the event */
  userId?: string;

  /** Human-readable description of the action performed */
  action: string;

  /** Type of resource accessed or modified (e.g. "policy", "tool", "role") */
  resource?: string;

  /** Unique identifier of the specific resource instance */
  resourceId?: string;

  /** Outcome of the operation */
  result: AuditResult;

  /** Client IP address, if available */
  ipAddress?: string;

  /** Client User-Agent string, if available */
  userAgent?: string;

  /** Arbitrary key-value details specific to the event */
  details?: Record<string, unknown>;

  /** Cross-service correlation / trace ID for distributed tracing */
  correlationId?: string;

  /** Severity level controlling log level and alerting thresholds */
  severity: AuditSeverity;
}

// ─── Severity → console level mapping ───────────────────────────────

const SEVERITY_LOG_LEVEL: Record<AuditSeverity, 'debug' | 'info' | 'warn' | 'error'> = {
  low: 'debug',
  medium: 'info',
  high: 'warn',
  critical: 'error',
};

/**
 * Maps an {@link AuditSeverity} to the corresponding Prisma AuditLog
 * `severity` string value stored in the database.
 */
const SEVERITY_TO_DB: Record<AuditSeverity, string> = {
  low: 'info',
  medium: 'info',
  high: 'warn',
  critical: 'critical',
};

/**
 * Maps an {@link AuditResult} to the corresponding Prisma AuditLog
 * `outcome` string value stored in the database.
 */
const RESULT_TO_DB: Record<AuditResult, string> = {
  success: 'success',
  failure: 'failure',
  denied: 'denied',
};

// ─── AuditLogger (Singleton) ────────────────────────────────────────

/**
 * Central audit logger for the Zenic-Agents gateway.
 *
 * Implements the **Singleton** pattern — use {@link AuditLogger.getInstance}
 * to obtain the shared instance.
 *
 * **Behaviour guarantees:**
 * 1. Every event is **always** written to the console as structured JSON,
 *    regardless of database availability.
 * 2. When the Prisma `AuditLog` table is reachable, the event is also
 *    persisted asynchronously. A database failure does **not** prevent
 *    the console log from being emitted (fail-open semantics).
 * 3. Database writes are fire-and-forget — errors are logged but never
 *    propagated to the caller, keeping the audit surface resilient.
 */
export class AuditLogger {
  private static instance: AuditLogger | null = null;

  /** Private to enforce singleton access via {@link getInstance}. */
  private constructor() {}

  /**
   * Returns the singleton {@link AuditLogger} instance, creating it on
   * first access.
   *
   * @example
   * ```ts
   * const logger = AuditLogger.getInstance();
   * logger.logAuth('user_123', 'login', 'success');
   * ```
   */
  public static getInstance(): AuditLogger {
    if (!AuditLogger.instance) {
      AuditLogger.instance = new AuditLogger();
    }
    return AuditLogger.instance;
  }

  /**
   * Reset the singleton (useful for testing).
   *
   * @internal
   */
  public static resetInstance(): void {
    AuditLogger.instance = null;
  }

  // ── Core logging method ─────────────────────────────────────────

  /**
   * Log a structured audit event.
   *
   * This is the lowest-level entry point. All convenience methods
   * (`logAuth`, `logDataAccess`, …) delegate here after constructing
   * the appropriate {@link AuditEvent}.
   *
   * The event is **always** written to the console as structured JSON.
   * When the database is reachable it is also persisted to the
   * `AuditLog` Prisma model; a DB failure is logged but never thrown.
   *
   * @param event - The fully-formed audit event to record.
   *
   * @example
   * ```ts
   * AuditLogger.getInstance().logEvent({
   *   timestamp: new Date().toISOString(),
   *   eventType: 'security_event',
   *   action: 'rate_limit_breach',
   *   result: 'denied',
   *   severity: 'high',
   *   details: { ip: '10.0.0.1', attempts: 150 },
   * });
   * ```
   */
  public logEvent(event: AuditEvent): void {
    // 1. Console output — always succeeds
    this.writeToConsole(event);

    // 2. Database persistence — fire-and-forget
    this.writeToDatabase(event).catch((err: unknown) => {
      const errorMessage = err instanceof Error ? err.message : String(err);
      console.error(
        JSON.stringify({
          level: 'error',
          message: '[AuditLogger] Failed to persist audit event to database',
          eventType: event.eventType,
          action: event.action,
          error: errorMessage,
          originalEvent: event,
        })
      );
    });
  }

  // ── Category-specific convenience methods ───────────────────────

  /**
   * Log an authentication / authorization event.
   *
   * Maps to {@link AuditEventType} `auth` with a default severity of
   * `low` for successes and `medium` for failures.
   *
   * @param userId   - ID of the user performing the auth action.
   * @param action   - Description of the auth action (e.g. `"login"`,
   *                   `"token_refresh"`, `"mfa_challenge"`).
   * @param result   - Whether the auth action succeeded or failed.
   * @param details  - Optional extra context (e.g. `mfaUsed: true`).
   *
   * @example
   * ```ts
   * logger.logAuth('user_42', 'login', 'success', { mfaUsed: true });
   * logger.logAuth('user_42', 'login', 'failure', { reason: 'wrong_password' });
   * ```
   */
  public logAuth(
    userId: string,
    action: string,
    result: AuditResult,
    details?: Record<string, unknown>
  ): void {
    this.logEvent({
      timestamp: new Date().toISOString(),
      eventType: 'auth',
      userId,
      action,
      result,
      severity: result === 'success' ? 'low' : 'medium',
      details,
    });
  }

  /**
   * Log a data access event (read, write, delete on a protected resource).
   *
   * Maps to {@link AuditEventType} `data_access` with a default severity
   * of `low`.
   *
   * @param userId     - ID of the user accessing the resource.
   * @param resource   - Type of resource (e.g. `"policy"`, `"tool"`, `"audit"`).
   * @param action     - Action performed (e.g. `"read"`, `"update"`, `"delete"`).
   * @param resourceId - Optional specific instance ID of the resource.
   *
   * @example
   * ```ts
   * logger.logDataAccess('user_42', 'policy', 'update', 'pol_abc123');
   * ```
   */
  public logDataAccess(
    userId: string,
    resource: string,
    action: string,
    resourceId?: string
  ): void {
    this.logEvent({
      timestamp: new Date().toISOString(),
      eventType: 'data_access',
      userId,
      action,
      resource,
      resourceId,
      result: 'success',
      severity: 'low',
    });
  }

  /**
   * Log an administrative action.
   *
   * Maps to {@link AuditEventType} `admin_action` with a default severity
   * of `medium`. Actions that modify RBAC assignments or system config are
   * elevated to `high`.
   *
   * @param userId  - ID of the admin performing the action.
   * @param action  - Description of the admin action (e.g. `"role.assign"`,
   *                  `"config.update"`, `"user.suspend"`).
   * @param target  - What was targeted (e.g. `"user:alice"`, `"role:admin"`).
   * @param details - Optional additional context.
   *
   * @example
   * ```ts
   * logger.logAdminAction('admin_1', 'role.assign', 'user:alice', {
   *   role: 'operator',
   *   grantedBy: 'admin_1',
   * });
   * ```
   */
  public logAdminAction(
    userId: string,
    action: string,
    target: string,
    details?: Record<string, unknown>
  ): void {
    const isHighRisk =
      action.startsWith('role.') ||
      action.startsWith('config.') ||
      action.startsWith('user.suspend') ||
      action.startsWith('user.delete');

    this.logEvent({
      timestamp: new Date().toISOString(),
      eventType: 'admin_action',
      userId,
      action,
      resource: target,
      result: 'success',
      severity: isHighRisk ? 'high' : 'medium',
      details,
    });
  }

  /**
   * Log a security-relevant event such as an intrusion attempt, policy
   * violation, or anomalous behaviour.
   *
   * Maps to {@link AuditEventType} `security_event`.
   *
   * @param type     - Specific security event type (e.g. `"brute_force"`,
   *                   `"rate_limit_breach"`, `"privilege_escalation_attempt"`).
   * @param severity - Severity level — use `critical` for events that
   *                   require immediate investigation.
   * @param details  - Context about the security event.
   *
   * @example
   * ```ts
   * logger.logSecurityEvent('brute_force', 'critical', {
   *   ip: '203.0.113.42',
   *   attempts: 47,
   *   window: '5m',
   * });
   * ```
   */
  public logSecurityEvent(
    type: string,
    severity: AuditSeverity,
    details: Record<string, unknown>
  ): void {
    this.logEvent({
      timestamp: new Date().toISOString(),
      eventType: 'security_event',
      action: type,
      result: 'denied',
      severity,
      details,
    });
  }

  // ── Private helpers ─────────────────────────────────────────────

  /**
   * Write the audit event to the console as structured JSON.
   *
   * The log level is determined by the event severity so that production
   * log aggregators can route messages appropriately.
   */
  private writeToConsole(event: AuditEvent): void {
    const level = SEVERITY_LOG_LEVEL[event.severity];
    const payload = {
      level,
      message: `[Audit] ${event.eventType}.${event.action}`,
      audit: event,
    };

    switch (level) {
      case 'error':
        console.error(JSON.stringify(payload));
        break;
      case 'warn':
        console.warn(JSON.stringify(payload));
        break;
      case 'info':
        console.info(JSON.stringify(payload));
        break;
      case 'debug':
      default:
        console.debug(JSON.stringify(payload));
        break;
    }
  }

  /**
   * Persist the audit event to the Prisma `AuditLog` table.
   *
   * Field mapping from {@link AuditEvent} → Prisma model:
   * - `userId`          → `actorId`
   * - `eventType`+`action` → `action`
   * - `resource`        → `resource`
   * - `resourceId`      → `resourceId`
   * - `severity`        → `severity` (mapped via {@link SEVERITY_TO_DB})
   * - `result`          → `outcome`  (mapped via {@link RESULT_TO_DB})
   * - `details`         → `details`  (JSON-serialised)
   * - `ipAddress`       → `ipAddress`
   * - `userAgent`       → `userAgent`
   * - `correlationId`   → `traceId`
   *
   * @returns A Promise that resolves when the DB write completes or
   *          rejects if the DB is unavailable. The caller is expected
   *          to `.catch()` rather than `await` this method.
   */
  private async writeToDatabase(event: AuditEvent): Promise<void> {
    try {
      await db.auditLog.create({
        data: {
          actorId: event.userId ?? 'system',
          actorType: event.userId ? 'user' : 'system',
          action: `${event.eventType}.${event.action}`,
          resource: event.resource ?? event.eventType,
          resourceId: event.resourceId ?? null,
          severity: SEVERITY_TO_DB[event.severity],
          outcome: RESULT_TO_DB[event.result],
          details: JSON.stringify(event.details ?? {}),
          ipAddress: event.ipAddress ?? null,
          userAgent: event.userAgent ?? null,
          traceId: event.correlationId ?? null,
          tags: JSON.stringify([event.eventType, event.severity]),
        },
      });
    } catch (error: unknown) {
      // Re-throw so the caller's .catch() can log the failure.
      // The console log was already emitted by writeToConsole, so we
      // never lose the event — just the DB persistence.
      throw error;
    }
  }
}

// ─── Route-Specific Audit Helpers ───────────────────────────────────

/**
 * Lazy-initialised singleton reference so helper functions don't need
 * to call {@link AuditLogger.getInstance} on every invocation.
 */
function logger(): AuditLogger {
  return AuditLogger.getInstance();
}

/**
 * Audit a Human-in-the-Loop (HITL) decision event.
 *
 * Covers approval, rejection, and escalation of HITL approval requests.
 * Maps to {@link AuditEventType} `hitl_decision` with severity `medium`
 * for standard decisions and `high` for escalations.
 *
 * @param requestId - The HITL approval request ID.
 * @param action    - The decision taken (e.g. `"approved"`, `"rejected"`,
 *                    `"escalated"`).
 * @param userId    - ID of the user who made the decision.
 * @param result    - Outcome string (e.g. `"approved"`, `"rejected"`,
 *                    `"escalated"`).
 *
 * @example
 * ```ts
 * auditHITLDecision('req_abc123', 'approved', 'user_42', 'approved');
 * auditHITLDecision('req_abc123', 'escalated', 'user_42', 'escalated');
 * ```
 */
export function auditHITLDecision(
  requestId: string,
  action: string,
  userId: string,
  result: string
): void {
  const isEscalation = action === 'escalated' || result === 'escalated';

  logger().logEvent({
    timestamp: new Date().toISOString(),
    eventType: 'hitl_decision',
    userId,
    action,
    resource: 'hitl_approval_request',
    resourceId: requestId,
    result: result === 'denied' ? 'denied' : result === 'failure' ? 'failure' : 'success',
    severity: isEscalation ? 'high' : 'medium',
    details: { requestId, decision: action, decisionResult: result },
  });
}

/**
 * Audit a tenant subscription change.
 *
 * Covers plan upgrades, downgrades, cancellations, and trial extensions.
 * Maps to {@link AuditEventType} `subscription` with severity `medium`
 * for standard changes and `high` for cancellations.
 *
 * @param tenantId - The tenant whose subscription changed.
 * @param action   - Description of the change (e.g. `"plan.upgrade"`,
 *                   `"plan.downgrade"`, `"plan.cancel"`,
 *                   `"trial.extend"`).
 * @param userId   - ID of the user who initiated the change.
 * @param details  - Context about the change (e.g. `fromPlan`, `toPlan`).
 *
 * @example
 * ```ts
 * auditSubscriptionChange('tenant_abc', 'plan.upgrade', 'user_42', {
 *   fromPlan: 'starter',
 *   toPlan: 'business',
 * });
 * ```
 */
export function auditSubscriptionChange(
  tenantId: string,
  action: string,
  userId: string,
  details: Record<string, unknown>
): void {
  const isCancellation = action === 'plan.cancel' || action.includes('cancel');

  logger().logEvent({
    timestamp: new Date().toISOString(),
    eventType: 'subscription',
    userId,
    action,
    resource: 'subscription',
    resourceId: tenantId,
    result: 'success',
    severity: isCancellation ? 'high' : 'medium',
    details: { tenantId, ...details },
  });
}

/**
 * Audit a payment-related operation.
 *
 * Covers charge attempts, refunds, invoice generation, and payment
 * failures. Maps to {@link AuditEventType} `payment` with severity
 * `medium` for successful charges and `high` for failures/refunds.
 *
 * @param tenantId - The tenant associated with the payment.
 * @param action   - Description of the payment action (e.g. `"charge"`,
 *                   `"refund"`, `"invoice.generate"`, `"payment.failed"`).
 * @param userId   - ID of the user or system principal triggering the action.
 * @param amount   - Optional monetary amount involved (in the tenant's
 *                   currency, typically USD cents or the smallest unit).
 *
 * @example
 * ```ts
 * auditPaymentAction('tenant_abc', 'charge', 'system', 2999);
 * auditPaymentAction('tenant_abc', 'payment.failed', 'system', 2999);
 * ```
 */
export function auditPaymentAction(
  tenantId: string,
  action: string,
  userId: string,
  amount?: number
): void {
  const isFailure = action.includes('failed') || action.includes('fail');
  const isRefund = action.includes('refund');

  logger().logEvent({
    timestamp: new Date().toISOString(),
    eventType: 'payment',
    userId,
    action,
    resource: 'payment',
    resourceId: tenantId,
    result: isFailure ? 'failure' : 'success',
    severity: isFailure || isRefund ? 'high' : 'medium',
    details: {
      tenantId,
      ...(amount !== undefined ? { amount } : {}),
    },
  });
}

// ─── Route Handler Integration Helper ───────────────────────────────

/**
 * Type for a standard route handler function compatible with Next.js
 * API routes or Express-style middleware.
 */
type RouteHandler = (
  req: Request & {
    /** Authenticated user ID, set by upstream auth middleware */
    userId?: string;
    /** Client IP extracted by the proxy / load balancer */
    ip?: string;
    /** Extracted correlation / trace ID */
    correlationId?: string;
  },
  ctx?: Record<string, unknown>
) => Promise<Response> | Response;

/**
 * Wraps a route handler to automatically emit an audit event for the
 * operation. The event is logged **after** the handler executes, using
 * the HTTP status code to determine the result:
 * - `2xx` → `success`
 * - `403` → `denied`
 * - Everything else → `failure`
 *
 * If the handler throws, a `failure` event is logged and the error is
 * re-thrown so upstream error handling remains unaffected.
 *
 * @typeParam T - The specific {@link AuditEventType} for this route.
 *
 * @param handler  - The original route handler to wrap.
 * @param eventType - The audit event category for this route.
 *
 * @returns A wrapped handler with identical signature that audits
 *          every invocation.
 *
 * @example
 * ```ts
 * // Next.js App Router API route
 * export const POST = withAuditLog(
 *   async (req) => {
 *     const body = await req.json();
 *     // … business logic …
 *     return Response.json({ ok: true });
 *   },
 *   'admin_action'
 * );
 * ```
 */
export function withAuditLog<T extends AuditEventType>(
  handler: RouteHandler,
  eventType: T
): RouteHandler {
  const instance = AuditLogger.getInstance();

  return async (req, ctx) => {
    const startTime = Date.now();
    const userId = req.userId;
    const ipAddress = req.ip;
    const correlationId = req.correlationId;
    const userAgent = req.headers?.get('user-agent') ?? undefined;

    try {
      const response = await handler(req, ctx);
      const duration = Date.now() - startTime;
      const status = response.status;

      let result: AuditResult;
      if (status >= 200 && status < 300) {
        result = 'success';
      } else if (status === 403) {
        result = 'denied';
      } else {
        result = 'failure';
      }

      const severity: AuditSeverity =
        result === 'denied'
          ? 'high'
          : result === 'failure'
            ? 'medium'
            : 'low';

      instance.logEvent({
        timestamp: new Date().toISOString(),
        eventType,
        userId,
        action: `${req.method} ${new URL(req.url).pathname}`,
        result,
        severity,
        ipAddress,
        userAgent,
        correlationId,
        details: {
          httpStatus: status,
          durationMs: duration,
          method: req.method,
          path: new URL(req.url).pathname,
        },
      });

      return response;
    } catch (error: unknown) {
      const duration = Date.now() - startTime;
      const errorMessage = error instanceof Error ? error.message : String(error);

      instance.logEvent({
        timestamp: new Date().toISOString(),
        eventType,
        userId,
        action: `${req.method} ${new URL(req.url).pathname}`,
        result: 'failure',
        severity: 'high',
        ipAddress,
        userAgent,
        correlationId,
        details: {
          error: errorMessage,
          durationMs: duration,
          method: req.method,
          path: new URL(req.url).pathname,
        },
      });

      throw error;
    }
  };
}
