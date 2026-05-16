// ─── Zenic-Agents v3 — OpenAI Function Calling Adapter ──────────────
// Converts OpenAI function calling format to MCP tools.
// Drop-in compatibility with Cline / Aide / OpenCode tool definitions.
//
// Pattern: Adapter Pattern — transforms external format to internal SDK.

import type {
  SdkToolConfig,
  SdkExecutionContext,
  SdkToolResult,
} from "../sdk/types";
import { getRegistry } from "../sdk/sdk";

// ─── OpenAI Type Definitions ─────────────────────────────────────────

/** OpenAI function parameter property */
export interface OpenAIParameterProperty {
  type: string;
  description?: string;
  enum?: string[];
  items?: OpenAIParameterProperty;
}

/** OpenAI function definition */
export interface OpenAIFunction {
  name: string;
  description: string;
  parameters: {
    type: "object";
    properties: Record<string, OpenAIParameterProperty>;
    required?: string[];
  };
}

/** OpenAI tool format */
export interface OpenAITool {
  type: "function";
  function: OpenAIFunction;
}

/** Options for registering an OpenAI tool */
export interface OpenAIToolOptions {
  category?: string;
  riskLevel?: SdkToolConfig["riskLevel"];
  permissions?: string[];
}

// ─── Registration Functions ───────────────────────────────────────────

/**
 * Register an OpenAI function calling tool as an MCP tool.
 * Drop-in compatibility with Cline/Aide/OpenCode.
 */
export function registerOpenAITool(
  tool: OpenAITool,
  handler: (
    args: Record<string, unknown>,
    ctx: SdkExecutionContext
  ) => Promise<SdkToolResult>,
  options?: OpenAIToolOptions
): void {
  const fn = tool.function;

  getRegistry().register(
    {
      name: fn.name,
      displayName: fn.name
        .replace(/_/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase()),
      description: fn.description,
      category: options?.category ?? "external",
      riskLevel: options?.riskLevel ?? "medium",
      inputSchema: fn.parameters as SdkToolConfig["inputSchema"],
      permissions: options?.permissions ?? [],
      handler,
    },
    "adapter_openai"
  );
}

/**
 * Bulk register OpenAI tools with a handler factory.
 * The factory receives the function name and returns the appropriate handler.
 */
export function registerOpenAITools(
  tools: OpenAITool[],
  handlerFactory: (
    name: string
  ) => (
    args: Record<string, unknown>,
    ctx: SdkExecutionContext
  ) => Promise<SdkToolResult>,
  options?: OpenAIToolOptions
): void {
  for (const tool of tools) {
    registerOpenAITool(tool, handlerFactory(tool.function.name), options);
  }
}
