// ─── Zenic-Agents v3 — MCP Gateway SDK ──────────────────────────────
// Main SDK entry point. Provides the mcpTool() function — the equivalent
// of the @mcp_tool decorator for declarative tool registration.
//
// Pattern: Singleton Registry — global registry ensures one source of truth.
// Pattern: Declarative Registration — mcpTool() as the primary API.

import type { SdkToolConfig } from "./types";
import { ToolRegistry } from "./tool-registry";

/** Global tool registry singleton */
let globalRegistry: ToolRegistry | null = null;

/** Get or create the global tool registry */
export function getRegistry(): ToolRegistry {
  if (!globalRegistry) {
    globalRegistry = new ToolRegistry();
  }
  return globalRegistry;
}

/**
 * Register an MCP tool — equivalent of @mcp_tool decorator.
 *
 * Usage:
 * ```typescript
 * mcpTool({
 *   name: "invoice_create",
 *   displayName: "Create Invoice",
 *   description: "Create a new invoice",
 *   category: "financial",
 *   riskLevel: "medium",
 *   permissions: ["financial:write"],
 *   rateLimit: 30,
 *   inputSchema: {
 *     type: "object",
 *     properties: {
 *       amount: { type: "number", description: "Invoice amount" },
 *       customer: { type: "string", description: "Customer name" },
 *     },
 *     required: ["amount", "customer"],
 *   },
 * }, async (input, ctx) => {
 *   const invoice = await createInvoice(input);
 *   return { success: true, data: invoice };
 * });
 * ```
 */
export function mcpTool<
  TInput = Record<string, unknown>,
  TOutput = Record<string, unknown>,
>(
  config: Omit<SdkToolConfig<TInput, TOutput>, "handler"> & {
    handler: SdkToolConfig<TInput, TOutput>["handler"];
  }
): void {
  getRegistry().register(config as SdkToolConfig, "sdk");
}

/** Reset the global registry (for testing) */
export function resetRegistry(): void {
  globalRegistry = null;
}
