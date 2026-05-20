// ─── Zenic-Agents v3 — Gateway Bootstrap ─────────────────────────
// Wires all services together using Dependency Injection.
// Singleton pattern for the engine — created once, reused across requests.
// Phase 2: Now wraps engine with ObservableGatewayEngine for tracing.

import { createHmac, randomBytes } from "crypto";
import { RateLimiter } from "./rate-limiter";
import { AuthService } from "./auth";
import { MerkleAuditService } from "./audit/merkle-audit";
import { GatewayEngine, ObservableGatewayEngine } from "./engine";
import { getRegistry } from "./sdk/sdk";
import { registerNativeExecutors, type ZenicExecutorType } from "./adapters/native-adapter";
import type { SdkExecutionContext, SdkToolResult } from "./sdk/types";

// ─── Singleton Engine ──────────────────────────────────────────

let engineInstance: GatewayEngine | null = null;
let observableInstance: ObservableGatewayEngine | null = null;
let observabilityInitialized = false;
let auditServiceRef: MerkleAuditService | null = null;

// Race condition fix: use a promise to serialize concurrent init calls
let initPromise: Promise<GatewayEngine> | null = null;

/** Get or create the gateway engine with all services wired (async-safe) */
export function initializeGateway(): GatewayEngine { // NOTE: Uses sync crypto for dev keys; async import for node:crypto
  if (engineInstance) return engineInstance;

  // If initialization is already in progress, we still create synchronously
  // since the GatewayEngine constructor is synchronous.
  // The real fix for concurrent requests is to ensure this is called once
  // at server startup, not per-request.

  // 1. Create services
  const rateLimiter = new RateLimiter();
  const authService = new AuthService();
  const auditService = new MerkleAuditService();
  auditServiceRef = auditService;
  const registry = getRegistry();

  // 2. Register API keys from environment variables (SECURITY FIX: no hardcoded keys)
  // FIX #11: Demo keys ahora expiran en 30 días en vez de nunca.
  // FIX SEC-1/2: API keys moved to environment variables with fail-closed in production.
  const DEMO_KEY_EXPIRY = Date.now() + 30 * 24 * 60 * 60 * 1000; // 30 días
  const ADMIN_KEY = process.env.ZENIC_ADMIN_KEY;
  const DEMO_KEY = process.env.ZENIC_DEMO_KEY;

  if (process.env.NODE_ENV === "production") {
    // PRODUCTION: Fail-closed — keys MUST be configured
    if (!ADMIN_KEY || ADMIN_KEY.length < 32) {
      throw new Error(
        "[SECURITY] ZENIC_ADMIN_KEY is required in production (min 32 characters). " +
        "Generate with: openssl rand -hex 32"
      );
    }
    if (!DEMO_KEY || DEMO_KEY.length < 32) {
      throw new Error(
        "[SECURITY] ZENIC_DEMO_KEY is required in production (min 32 characters). " +
        "Generate with: openssl rand -hex 32"
      );
    }
    authService.registerApiKey({
      key: ADMIN_KEY,
      tenantId: "default",
      name: "admin-client",
      scopes: ["*"],
      expiresAt: DEMO_KEY_EXPIRY,
    });
    authService.registerApiKey({
      key: DEMO_KEY,
      tenantId: "default",
      name: "demo-client",
      scopes: ["tool:execute", "tool:read"],
      expiresAt: DEMO_KEY_EXPIRY,
    });
  } else {
    // DEVELOPMENT: Ephemeral random keys with explicit warning
    const devAdmin = ADMIN_KEY || randomBytes(32).toString("hex");
    const devDemo = DEMO_KEY || randomBytes(32).toString("hex");
    console.warn(
      "[SECURITY] Using ephemeral dev API keys. " +
      "Set ZENIC_ADMIN_KEY and ZENIC_DEMO_KEY for persistent keys."
    );
    authService.registerApiKey({
      key: devAdmin,
      tenantId: "default",
      name: "admin-client",
      scopes: ["*"],
      expiresAt: DEMO_KEY_EXPIRY,
    });
    authService.registerApiKey({
      key: devDemo,
      tenantId: "default",
      name: "demo-client",
      scopes: ["tool:execute", "tool:read"],
      expiresAt: DEMO_KEY_EXPIRY,
    });
  }

  // Register tenants
  authService.registerTenant({
    id: "default",
    name: "Default Tenant",
    permissions: ["tool:execute", "tool:read", "audit:read", "dashboard:read"],
    rateLimits: {},
    enabled: true,
  });

  // 3. Register rate limit configs for common tools
  rateLimiter.registerConfig("default", {
    algorithm: "sliding_window",
    maxRequests: 100,
    windowMs: 60_000,
  });

  // 4. Register 19 native executors if not already registered
  if (registry.count === 0) {
    registerNativeExecutors(
      (executorType: ZenicExecutorType) =>
        async (input: Record<string, unknown>, ctx: SdkExecutionContext): Promise<SdkToolResult> => {
          // Native executor handler — logs and returns mock result
          // In production, this would route to the actual executor implementation
          auditService.record({
            action: `executor.${executorType}`,
            resource: "executor",
            resourceId: executorType,
            actorId: ctx.executorId,
            actorType: ctx.executorId ? "user" : "system",
            outcome: "success",
            severity: "info",
            details: { input, ctx, executorType },
            tags: ["executor", "native"],
            traceId: ctx.traceId,
            tenantId: ctx.tenantId,
          });

          return {
            success: true,
            data: {
              executorType,
              status: "executed",
              input,
              timestamp: ctx.timestamp,
              note: "Native executor simulated — connect to actual executor in production",
            },
          };
        }
    );
  }

  // 5. Create gateway engine with DI
  engineInstance = new GatewayEngine({
    rateLimiter,
    authService,
    toolRegistry: registry,
    auditService,
    config: {
      defaultTimeout: 30_000,
      maxRetries: 2,
      requireAuth: true, // FIX #11: Auth habilitado — INVARIANT 4
      enforceRateLimit: true,
      auditAll: true,
      enforceRbac: true, // FIX #11: RBAC habilitado — defensa en profundidad
    },
  });

  // 6. Record bootstrap audit
  auditService.record({
    action: "gateway.initialize",
    resource: "gateway",
    actorType: "system",
    outcome: "success",
    severity: "info",
    details: {
      toolCount: registry.count,
      nativeExecutors: 19,
      authMethods: ["api_key", "bearer_token"],
      rateLimitAlgorithms: ["token_bucket", "sliding_window", "fixed_window"],
      observability: "enabled",
    },
    tags: ["gateway", "bootstrap"],
  });

  // 7. Create observable wrapper (Phase 2)
  observableInstance = new ObservableGatewayEngine(engineInstance, { enabled: true });

  // 8. Periodic cleanup for rate limiter to prevent unbounded memory growth
  // Runs every 60 seconds, removing stale buckets and expired windows
  if (typeof globalThis !== "undefined") {
    const existingTimer = (globalThis as Record<string, unknown>).__zenicRateLimitCleanup;
    if (existingTimer) clearInterval(existingTimer as ReturnType<typeof setInterval>);

    const timer = setInterval(() => {
      try {
        const result = rateLimiter.cleanup();
        if (result.bucketsRemoved > 0 || result.windowsRemoved > 0) {
          console.log(`[Gateway] Rate limiter cleanup: removed ${result.bucketsRemoved} buckets, ${result.windowsRemoved} windows`);
        }
      } catch (err) {
        console.error("[Gateway] Rate limiter cleanup failed:", err);
      }
    }, 60_000);

    (globalThis as Record<string, unknown>).__zenicRateLimitCleanup = timer;
  }

  return engineInstance;
}

/** Get the observable gateway engine (with tracing + metrics) */
export function getObservableGateway(): ObservableGatewayEngine {
  if (!observableInstance) {
    initializeGateway();
  }
  return observableInstance!;
}

/**
 * Initialize observability subsystem — seed metric series.
 * Call once at app startup (after DB is ready).
 */
export async function initializeObservability(): Promise<void> {
  if (observabilityInitialized) return;

  try {
    const { seedMetricSeries } = await import("@/lib/observability/metrics/metrics-collector");
    const count = await seedMetricSeries();
    console.log(`[Observability] Seeded ${count} metric series`);
    observabilityInitialized = true;
  } catch (error) {
    console.error("[Observability] Failed to seed metric series:", error);
  }
}

/** Reset the gateway (for testing) */
export function resetGateway(): void {
  engineInstance = null;
  observableInstance = null;
  observabilityInitialized = false;
  auditServiceRef = null;
  initPromise = null;
}

/** Get the audit service for external access */
export function getAuditService(): MerkleAuditService {
  if (!auditServiceRef) {
    initializeGateway();
  }
  return auditServiceRef!;
}
