// ─── Zenic-Agents MCP Gateway — Gateway Engine ─────────────────────────
// Main orchestration engine for the MCP Gateway evaluation pipeline.
//
// Pipeline Pattern: 8-step sequential evaluation
// Chain of Responsibility: each step can short-circuit the pipeline
//
// Flow:
//   Client Request → Tool Resolution → Auth Check → Rate Limit Check
//     → RBAC Check → Policy Engine Check → Risk/Policy Check → Tool Execute
//     → Audit Record (Merkle) → Response
//
// Dependency Inversion: all services are injected via constructor.
// Lazy imports are used for DB, RBAC, and PolicyEngine to avoid circular deps.

import { randomUUID } from "crypto";
import type { GatewayRequest, GatewayResponse, GatewayPipelineStep, GatewayConfig } from "./types";
import type { RateLimiter } from "../rate-limiter/rate-limiter";
import type { AuthService } from "../auth/auth-service";
import type { ToolRegistry } from "../sdk/tool-registry";
import type { MerkleAuditService } from "../audit/merkle-audit";
import type { RateLimitResult } from "../rate-limiter/types";
import type { RateLimitKey } from "../rate-limiter/types";
import { RISK_LEVEL_CONFIG } from "../types";

// ── Lazy import cache (H-91 fix: avoid repeated dynamic imports in hot path) ──
let _rbacModule: Promise<any> | null = null;
let _policyModule: Promise<any> | null = null;
let _dbModule: Promise<any> | null = null;

const DEFAULT_CONFIG: GatewayConfig = {
  defaultTimeout: 30000,
  maxRetries: 2,
  requireAuth: true,
  enforceRateLimit: true,
  auditAll: true,
  enforceRbac: true,
};

export class GatewayEngine {
  private config: GatewayConfig;
  private rateLimiter: RateLimiter;
  private authService: AuthService;
  private toolRegistry: ToolRegistry;
  private auditService: MerkleAuditService;

  constructor(deps: {
    rateLimiter: RateLimiter;
    authService: AuthService;
    toolRegistry: ToolRegistry;
    auditService: MerkleAuditService;
    config?: Partial<GatewayConfig>;
  }) {
    this.rateLimiter = deps.rateLimiter;
    this.authService = deps.authService;
    this.toolRegistry = deps.toolRegistry;
    this.auditService = deps.auditService;
    this.config = { ...DEFAULT_CONFIG, ...deps.config };
  }

  /**
   * Main gateway entry point.
   * Executes the full evaluation pipeline and returns a verdict.
   */
  async execute(request: GatewayRequest): Promise<GatewayResponse> {
    const startTime = Date.now();
    const executionId = this.generateExecutionId();
    const pipeline: GatewayPipelineStep[] = [];

    // ─── Step 1: Tool Resolution ────────────────────────
    const toolStep = this.measureStep("tool_resolution", () => {
      const tool = this.toolRegistry.get(request.toolCall.name);
      if (!tool) {
        return { passed: false, reason: `Tool "${request.toolCall.name}" not found in registry` };
      }
      return { passed: true, details: { category: tool.config.category, riskLevel: tool.config.riskLevel } };
    });
    pipeline.push(toolStep);

    if (!toolStep.passed) {
      return this.buildResponse(executionId, "deny", toolStep.reason!, pipeline, startTime);
    }

    const tool = this.toolRegistry.get(request.toolCall.name)!;

    // ─── Step 2: Auth Check ─────────────────────────────
    if (this.config.requireAuth) {
      const authStep = this.measureStep("auth_check", () => {
        if (!request.auth.authenticated) {
          return { passed: false, reason: request.auth.error ?? "Authentication required" };
        }
        return { passed: true, details: { method: request.auth.method, tenantId: request.auth.tenantId } };
      });
      pipeline.push(authStep);

      if (!authStep.passed) {
        return this.buildResponse(executionId, "deny", authStep.reason!, pipeline, startTime);
      }
    }

    // ─── Step 3: Rate Limit Check ───────────────────────
    if (this.config.enforceRateLimit) {
      const rateLimitKey: RateLimitKey = {
        toolName: request.toolCall.name,
        tenantId: request.auth.tenantId,
        executorId: request.auth.executorId,
      };

      const rateStep = this.measureStep("rate_limit", () => {
        const result = this.rateLimiter.check(rateLimitKey, {
          algorithm: "sliding_window",
          maxRequests: tool.config.rateLimit ?? 100,
          windowMs: 60000,
        });
        return {
          passed: result.allowed,
          details: result as unknown as Record<string, unknown>,
          reason: result.allowed ? undefined : `Rate limit exceeded. Retry after ${result.retryAfterMs}ms`,
        };
      });
      pipeline.push(rateStep);

      if (!rateStep.passed) {
        return this.buildResponse(
          executionId,
          "deny",
          rateStep.reason!,
          pipeline,
          startTime,
          rateStep.details as unknown as RateLimitResult,
        );
      }
    }

    // ─── Step 4: RBAC Check ─────────────────────────────
    if (this.config.enforceRbac && request.auth.executorId) {
      const rbacStep = await this.measureStepAsync("rbac_check", async () => {
        // Lazy import to avoid circular dependencies (H-91: cached)
        if (!_rbacModule) _rbacModule = import("../services/rbac-service");
        const { checkPermission } = await _rbacModule;
        const result = await checkPermission({
          userId: request.auth.executorId!,
          resource: "tool",
          action: "execute",
          context: { toolName: request.toolCall.name, category: tool.config.category, riskLevel: tool.config.riskLevel },
        });
        return {
          passed: result.allowed,
          reason: result.allowed ? undefined : result.reason,
          details: { matchedPolicies: result.matchedPolicies, constraints: result.constraints },
        };
      });
      pipeline.push(rbacStep);

      if (!rbacStep.passed) {
        return this.buildResponse(executionId, "deny", rbacStep.reason!, pipeline, startTime);
      }
    }

    // ─── Step 5: Policy Engine Check (Phase 3) ─────────
    // Evaluate declarative policies from the Policy Engine.
    // This step checks resource/action against compiled YAML policies.
    const policyStep = await this.measureStepAsync("policy_engine", async () => {
      try {
        // H-91: cached lazy import for policy engine
        if (!_policyModule) _policyModule = import("@/lib/policy-engine/evaluator");
        const { getPolicyEvaluator } = await _policyModule;
        const evaluator = getPolicyEvaluator();
        const result = await evaluator.evaluate({
          resource: `${tool.config.category}/${request.toolCall.name}`,
          action: "execute",
          context: {
            ...request.toolCall.arguments as Record<string, unknown>,
            riskLevel: tool.config.riskLevel,
            category: tool.config.category,
          },
          tenantId: request.auth.tenantId,
          userId: request.auth.executorId,
        });

        if (result.effect === "deny") {
          return {
            passed: false,
            reason: `Policy engine denied: ${result.reason}`,
            details: {
              policyId: result.policyId,
              matchedStatementId: result.matchedStatementId,
              matchedCount: result.matchedStatements.length,
              denyByDefault: result.denyByDefault,
            },
          };
        }

        if (result.effect === "conditional") {
          return {
            passed: false,
            reason: `Policy engine requires approval: ${result.reason}`,
            details: {
              policyId: result.policyId,
              matchedStatementId: result.matchedStatementId,
              requiredRole: result.requiredRole,
              effect: "conditional",
            },
          };
        }

        return {
          passed: true,
          details: {
            policyId: result.policyId,
            matchedStatementId: result.matchedStatementId,
            matchedCount: result.matchedStatements.length,
          },
        };
      } catch {
        // FIX #3 CRÍTICO: INVARIANT 4 — DENY es absoluto.
        // Antes: fail-open (allow si policy engine no disponible).
        // Ahora: fail-closed (DENY si no se puede evaluar la política).
        // En producción, un policy engine caído significa que NO se puede
        // garantizar la seguridad → la acción DEBE ser denegada.
        return {
          passed: false,
          reason: "Policy engine unavailable — denying by default (INVARIANT 4: DENY is absolute)",
          details: { policyEngine: "unavailable", failClosed: true },
        };
      }
    });
    pipeline.push(policyStep);

    if (!policyStep.passed) {
      // Check if it's a conditional (needs approval) vs hard deny
      const isConditional = (policyStep.details as Record<string, unknown>)?.effect === "conditional";
      if (isConditional) {
        return this.buildResponse(executionId, "conditional", policyStep.reason!, pipeline, startTime);
      }
      return this.buildResponse(executionId, "deny", policyStep.reason!, pipeline, startTime);
    }

    // ─── Step 6: Risk/Policy Check ──────────────────────
    const riskConfig = RISK_LEVEL_CONFIG[tool.config.riskLevel as keyof typeof RISK_LEVEL_CONFIG];
    if (riskConfig?.requiresApproval || tool.config.requiresApproval) {
      const riskStep = this.measureStep("risk_policy", () => ({
        passed: false,
        reason: `Tool risk level "${tool.config.riskLevel}" requires human approval`,
        details: { requiresApproval: true, riskLevel: tool.config.riskLevel },
      }));
      pipeline.push(riskStep);

      // Record pending execution in DB (lazy import)
      try {
        // H-91: cached lazy import for DB
        if (!_dbModule) _dbModule = import("@/lib/db");
        const { db } = await _dbModule;
        await db.toolExecution.create({
          data: {
            id: executionId,
            toolId: request.toolCall.name, // Using name as reference
            executorId: request.auth.executorId,
            status: "pending",
            input: JSON.stringify(request.toolCall.arguments),
            verdict: "conditional",
            verdictReason: riskStep.reason,
            correlationId: request.toolCall._meta?.traceId,
          },
        });
      } catch {
        // DB not available, continue
      }

      return this.buildResponse(executionId, "conditional", riskStep.reason!, pipeline, startTime);
    }

    // ─── Step 7: Execute Tool ───────────────────────────
    const executeStep = await this.measureStepAsync("tool_execution", async () => {
      try {
        const result = await this.toolRegistry.execute(request.toolCall.name, request.toolCall.arguments, {
          executorId: request.auth.executorId,
          tenantId: request.auth.tenantId,
          traceId: request.toolCall._meta?.traceId,
          timestamp: Date.now(),
        });
        return {
          passed: result.success,
          details: result as unknown as Record<string, unknown>,
          reason: result.success ? undefined : result.error,
        };
      } catch (error) {
        return { passed: false, reason: error instanceof Error ? error.message : "Execution failed" };
      }
    });
    pipeline.push(executeStep);

    // ─── Step 8: Audit Record (Merkle) ──────────────────
    if (this.config.auditAll) {
      this.auditService.record({
        action: "tool.execute",
        resource: "tool",
        resourceId: request.toolCall.name,
        actorId: request.auth.executorId,
        actorType: request.auth.executorId ? "user" : "system",
        outcome: executeStep.passed ? "success" : "failure",
        severity: executeStep.passed ? "info" : "warn",
        details: {
          toolName: request.toolCall.name,
          verdict: "allow",
          executionId,
          duration: executeStep.duration,
        },
        tags: ["gateway", "execution", tool.config.category],
        traceId: request.toolCall._meta?.traceId,
        tenantId: request.auth.tenantId,
        duration: Date.now() - startTime,
      });
    }

    // ─── Build Response ─────────────────────────────────
    const verdict = executeStep.passed ? "allow" : "deny";
    const reason = executeStep.passed
      ? "All checks passed — execution authorized"
      : executeStep.reason ?? "Execution failed";

    const mcpResult = executeStep.passed && executeStep.details
      ? {
          content: [{ type: "text" as const, text: JSON.stringify((executeStep.details as Record<string, unknown>).data ?? executeStep.details) }],
          _meta: { executionId, verdict, duration: Date.now() - startTime },
        }
      : {
          content: [{ type: "text" as const, text: reason }],
          isError: true as const,
          _meta: { executionId, verdict, duration: Date.now() - startTime },
        };

    return {
      verdict,
      reason,
      result: mcpResult,
      executionId,
      pipeline,
      duration: Date.now() - startTime,
    };
  }

  // ─── Helpers ───────────────────────────────────────────

  private measureStep(
    name: string,
    fn: () => { passed: boolean; reason?: string; details?: unknown },
  ): GatewayPipelineStep {
    const start = Date.now();
    const result = fn();
    return {
      name,
      ...result,
      duration: Date.now() - start,
      details: result.details as Record<string, unknown> | undefined,
    };
  }

  private async measureStepAsync(
    name: string,
    fn: () => Promise<{ passed: boolean; reason?: string; details?: unknown }>,
  ): Promise<GatewayPipelineStep> {
    const start = Date.now();
    const result = await fn();
    return {
      name,
      ...result,
      duration: Date.now() - start,
      details: result.details as Record<string, unknown> | undefined,
    };
  }

  private buildResponse(
    executionId: string,
    verdict: "allow" | "deny" | "conditional",
    reason: string,
    pipeline: GatewayPipelineStep[],
    startTime: number,
    rateLimit?: RateLimitResult,
  ): GatewayResponse {
    return {
      verdict,
      reason,
      executionId,
      pipeline,
      rateLimit,
      duration: Date.now() - startTime,
    };
  }

  private generateExecutionId(): string {
    return `exec_${Date.now().toString(36)}_${randomUUID().slice(0, 8)}`;
  }
}
