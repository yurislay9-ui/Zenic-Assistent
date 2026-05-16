// ─── Zenic-Agents v3 — SDK Type Definitions ─────────────────────────
// Type-safe tool registration types for the MCP Gateway SDK.
// Zero Big objects — each interface has single responsibility.

import type { McpToolDefinition, McpToolAnnotations } from "../protocol/types";

// ─── Tool Configuration ──────────────────────────────────────────────

/** Tool registration via SDK */
export interface SdkToolConfig<
  TInput = Record<string, unknown>,
  TOutput = Record<string, unknown>,
> {
  /** Unique tool name (lowercase, underscores) */
  name: string;
  /** Human-readable name */
  displayName: string;
  /** Description of what the tool does */
  description: string;
  /** Tool category */
  category: string;
  /** Risk level */
  riskLevel: "low" | "medium" | "high" | "critical";
  /** MCP input schema */
  inputSchema: McpToolDefinition["inputSchema"];
  /** MCP output schema (optional) */
  outputSchema?: McpToolDefinition["inputSchema"];
  /** MCP tool annotations */
  annotations?: McpToolAnnotations;
  /** Required permissions to execute */
  permissions: string[];
  /** Rate limit: max calls per minute */
  rateLimit?: number;
  /** Requires human approval */
  requiresApproval?: boolean;
  /** Execution timeout in ms */
  timeout?: number;
  /** Max retries */
  retries?: number;
  /** Tags for filtering */
  tags?: string[];
  /** The actual handler function */
  handler: SdkToolHandler<TInput, TOutput>;
}

// ─── Handler Function ────────────────────────────────────────────────

/** Tool handler function type */
export type SdkToolHandler<
  TInput = Record<string, unknown>,
  TOutput = Record<string, unknown>,
> = (
  input: TInput,
  context: SdkExecutionContext
) => Promise<SdkToolResult<TOutput>>;

// ─── Execution Context ───────────────────────────────────────────────

/** Execution context provided to tool handlers */
export interface SdkExecutionContext {
  /** Who is executing */
  executorId?: string;
  /** Tenant ID */
  tenantId?: string;
  /** Trace ID for correlation */
  traceId?: string;
  /** Request timestamp */
  timestamp: number;
  /** Abort signal for cancellation */
  signal?: AbortSignal;
}

// ─── Tool Result ─────────────────────────────────────────────────────

/** Tool execution result */
export interface SdkToolResult<
  TOutput = Record<string, unknown>,
> {
  success: boolean;
  data?: TOutput;
  error?: string;
  /** Duration in ms (auto-filled if not provided) */
  duration?: number;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
}

// ─── Registry Entry ──────────────────────────────────────────────────

/** Tool registry entry (internal) */
export interface SdkToolRegistryEntry {
  config: SdkToolConfig;
  registeredAt: number;
  source: "sdk" | "adapter_openai" | "adapter_native" | "adapter_langchain";
}
