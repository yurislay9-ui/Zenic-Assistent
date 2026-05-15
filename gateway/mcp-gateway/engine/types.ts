// ─── Zenic-Agents MCP Gateway — Engine Type System ─────────────────────
// Gateway evaluation pipeline types — Pipeline Pattern + Chain of Responsibility

import type { McpToolCallParams, McpToolCallResult } from "../protocol/types";
import type { AuthResult } from "../auth/types";
import type { RateLimitResult } from "../rate-limiter/types";

/** Gateway execution request */
export interface GatewayRequest {
  /** JSON-RPC request ID */
  requestId: string | number | null;
  /** Tool call parameters */
  toolCall: McpToolCallParams;
  /** Authentication result */
  auth: AuthResult;
  /** Client IP */
  ipAddress?: string;
  /** Client user agent */
  userAgent?: string;
}

/** Gateway execution response */
export interface GatewayResponse {
  /** The verdict: allow, deny, or conditional (needs approval) */
  verdict: "allow" | "deny" | "conditional";
  /** Human-readable reason */
  reason: string;
  /** Tool call result (if allowed and executed) */
  result?: McpToolCallResult;
  /** Rate limit info */
  rateLimit?: RateLimitResult;
  /** Execution ID for tracking */
  executionId: string;
  /** Pipeline steps that were evaluated */
  pipeline: GatewayPipelineStep[];
  /** Total evaluation + execution time in ms */
  duration: number;
}

/** A single step in the gateway evaluation pipeline */
export interface GatewayPipelineStep {
  name: string;
  passed: boolean;
  reason?: string;
  duration: number;
  details?: Record<string, unknown>;
}

/** Gateway configuration */
export interface GatewayConfig {
  /** Default timeout for tool execution (ms) */
  defaultTimeout: number;
  /** Maximum retries for tool execution */
  maxRetries: number;
  /** Whether to require auth for all calls */
  requireAuth: boolean;
  /** Whether to enforce rate limiting */
  enforceRateLimit: boolean;
  /** Whether to record audit for all calls */
  auditAll: boolean;
  /** Whether to enforce RBAC */
  enforceRbac: boolean;
}
