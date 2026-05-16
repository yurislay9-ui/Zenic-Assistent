// ─── Zenic-Agents MCP Gateway — Gateway Engine Service ────────────────
// Functional gateway engine — used by API routes for execution evaluation.
// This is the simpler, functional interface that wraps the class-based
// GatewayEngine for use in Next.js API route handlers.

import { db } from "@/lib/db";
import type { ExecutionRequest, VerdictResponse } from "../types";

/**
 * Evaluate whether a tool execution should be allowed, denied, or require approval.
 * This is the primary gateway evaluation function used by API routes.
 */
export async function evaluateExecution(request: ExecutionRequest): Promise<VerdictResponse> {
  const { toolName, input, executorId, correlationId, bypassApproval } = request;

  try {
    // Look up the tool in the registry
    const tool = await db.mcpTool.findUnique({
      where: { name: toolName },
    });

    if (!tool) {
      return {
        verdict: "deny",
        reason: `Tool "${toolName}" not found in registry`,
        requiresApproval: false,
      };
    }

    // Check if tool is active
    if (tool.status === "disabled") {
      return {
        verdict: "deny",
        reason: `Tool "${toolName}" is currently disabled`,
        requiresApproval: false,
      };
    }

    // Check if tool is deprecated
    if (tool.status === "deprecated") {
      // Still allow but warn
    }

    // Risk-based approval check
    const riskConfig = {
      low: { requiresApproval: false },
      medium: { requiresApproval: false },
      high: { requiresApproval: true },
      critical: { requiresApproval: true },
    };

    const riskLevel = (tool.riskLevel as keyof typeof riskConfig) ?? "low";
    const needsApproval = !bypassApproval && (riskConfig[riskLevel]?.requiresApproval || tool.requiresApproval);

    if (needsApproval) {
      // Create pending execution record
      const execution = await db.toolExecution.create({
        data: {
          toolId: tool.id,
          executorId: executorId ?? null,
          status: "pending",
          input: JSON.stringify(input),
          verdict: "conditional",
          verdictReason: `Tool risk level "${tool.riskLevel}" requires human approval`,
          correlationId,
        },
      });

      return {
        verdict: "conditional",
        reason: `Tool risk level "${tool.riskLevel}" requires human approval`,
        executionId: execution.id,
        requiresApproval: true,
        conditions: [`Risk level: ${tool.riskLevel}`, `Approval required before execution`],
      };
    }

    // Execute the tool (simulation — in production this would call the actual MCP server)
    const executionId = `exec_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

    try {
      const startTime = Date.now();

      // Create execution record
      await db.toolExecution.create({
        data: {
          id: executionId,
          toolId: tool.id,
          executorId: executorId ?? null,
          status: "completed",
          input: JSON.stringify(input),
          output: JSON.stringify({ success: true, toolName, input }),
          duration: Date.now() - startTime,
          verdict: "allow",
          verdictReason: "All checks passed — execution authorized",
          correlationId,
        },
      });

      return {
        verdict: "allow",
        reason: "All checks passed — execution authorized",
        executionId,
        requiresApproval: false,
      };
    } catch (execError) {
      // Record failed execution
      await db.toolExecution.create({
        data: {
          id: executionId,
          toolId: tool.id,
          executorId: executorId ?? null,
          status: "failed",
          input: JSON.stringify(input),
          errorMessage: execError instanceof Error ? execError.message : "Execution failed",
          verdict: "deny",
          verdictReason: "Tool execution failed",
          correlationId,
        },
      }).catch(() => {
        // Don't fail the response if audit logging fails
      });

      return {
        verdict: "deny",
        reason: execError instanceof Error ? execError.message : "Tool execution failed",
        requiresApproval: false,
      };
    }
  } catch (error) {
    console.error("[evaluateExecution]", error);
    return {
      verdict: "deny",
      reason: "Internal gateway error",
      requiresApproval: false,
    };
  }
}

/**
 * Approve a pending execution.
 */
export async function approveExecution(executionId: string, approverId: string) {
  const execution = await db.toolExecution.update({
    where: { id: executionId, status: "pending" },
    data: {
      status: "approved",
      verdict: "allow",
      verdictReason: `Approved by ${approverId}`,
      completedAt: new Date(),
    },
  });

  return execution;
}

/**
 * Deny a pending execution.
 */
export async function denyExecution(executionId: string, denierId: string, reason: string) {
  const execution = await db.toolExecution.update({
    where: { id: executionId, status: "pending" },
    data: {
      status: "denied",
      verdict: "deny",
      verdictReason: `Denied by ${denierId}: ${reason}`,
      completedAt: new Date(),
    },
  });

  return execution;
}
