// ─── Zenic-Agents v3 — Gateway Bootstrap ─────────────────────────
// Wires all services together using Dependency Injection.
// Singleton pattern for the engine — created once, reused across requests.
// Phase 2: Now wraps engine with ObservableGatewayEngine for tracing.

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

/** Get or create the gateway engine with all services wired */
export function initializeGateway(): GatewayEngine {
  if (engineInstance) return engineInstance;

  // 1. Create services
  const rateLimiter = new RateLimiter();
  const authService = new AuthService();
  const auditService = new MerkleAuditService();
  const registry = getRegistry();

  // 2. Register default API keys (demo)
  authService.registerApiKey({
    key: "zenic_demo_key_2024",
    tenantId: "default",
    name: "demo-client",
    scopes: ["tool:execute", "tool:read"],
    expiresAt: undefined, // never expires
  });

  authService.registerApiKey({
    key: "zenic_admin_key_2024",
    tenantId: "default",
    name: "admin-client",
    scopes: ["*"],
    expiresAt: undefined,
  });

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
      requireAuth: false, // Allow unauthenticated for development
      enforceRateLimit: true,
      auditAll: true,
      enforceRbac: false, // Disable RBAC for development (no DB dependency in hot path)
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
}

/** Get the audit service for external access */
export function getAuditService(): MerkleAuditService {
  return initializeGateway()["auditService"];
}
