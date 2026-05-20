// ─── Zenic-Agents v3 — Native Executor Adapter ──────────────────────
// Registers the 19 existing Zenic executor types as MCP tools.
// Each executor gets a proper inputSchema, permissions, and risk level.
//
// Pattern: Adapter Pattern — converts native executor definitions to SDK tools.
// Pattern: Factory Pattern — handlerFactory creates per-executor handlers.

import { getRegistry } from "../../sdk/sdk";
import type {
  SdkExecutionContext,
  SdkToolResult,
} from "../../sdk/types";
import {
  ZENIC_EXECUTOR_TYPES,
  type ZenicExecutorType,
  EXECUTOR_SCHEMAS,
  type ExecutorSchemaDef,
} from "./_handlers";

// Re-export types for backward compatibility
export { ZENIC_EXECUTOR_TYPES, type ZenicExecutorType, type ExecutorSchemaDef };

// ─── Registration ────────────────────────────────────────────────────

/**
 * Register all 19 native Zenic executors as MCP tools.
 * Each executor gets proper inputSchema, permissions, and risk level.
 */
export function registerNativeExecutors(
  handlerFactory: (
    executorType: ZenicExecutorType
  ) => (
    input: Record<string, unknown>,
    ctx: SdkExecutionContext
  ) => Promise<SdkToolResult>
): void {
  const registry = getRegistry();

  for (const [executorType, schema] of Object.entries(EXECUTOR_SCHEMAS) as [
    ZenicExecutorType,
    ExecutorSchemaDef,
  ][]) {
    registry.register(
      {
        name: `zenic_${executorType}`,
        displayName: executorType
          .replace(/_/g, " ")
          .replace(/\b\w/g, (c) => c.toUpperCase()),
        description: schema.description,
        category: schema.category,
        riskLevel: schema.riskLevel,
        inputSchema: schema.inputSchema,
        permissions: schema.permissions,
        rateLimit:
          schema.riskLevel === "critical"
            ? 5
            : schema.riskLevel === "high"
              ? 20
              : 60,
        requiresApproval:
          schema.riskLevel === "critical" || schema.riskLevel === "high",
        timeout: schema.riskLevel === "critical" ? 60000 : 30000,
        handler: handlerFactory(executorType),
      },
      "adapter_native"
    );
  }
}
