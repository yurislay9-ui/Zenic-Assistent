// ─── Zenic-Agents MCP Gateway — Tool Registry (SDK) ──────────────────
// In-memory tool registry for MCP tool management.
// Tools are registered with their config and execution handler.

import type { SdkToolConfig, SdkExecutionContext, SdkToolResult } from "./types";

/** Registered tool entry */
export interface RegisteredTool {
  config: SdkToolConfig;
  source: "sdk" | "adapter_openai" | "adapter_native" | "adapter_langchain";
  registeredAt: number;
}

export class ToolRegistry {
  private tools = new Map<string, RegisteredTool>();

  /** Register a tool with its config */
  register(config: SdkToolConfig, source: RegisteredTool["source"] = "sdk"): void {
    if (this.tools.has(config.name)) {
      throw new Error(`Tool "${config.name}" is already registered`);
    }
    this.tools.set(config.name, { config, source, registeredAt: Date.now() });
  }

  /** Unregister a tool by name */
  unregister(name: string): boolean {
    return this.tools.delete(name);
  }

  /** Get a registered tool by name */
  get(name: string): RegisteredTool | undefined {
    return this.tools.get(name);
  }

  /** Check if a tool is registered */
  has(name: string): boolean {
    return this.tools.has(name);
  }

  /** List all registered tools */
  list(filter?: { category?: string; riskLevel?: string; source?: string }): RegisteredTool[] {
    const entries = Array.from(this.tools.values());
    if (!filter) return entries;
    return entries.filter((entry) => {
      if (filter.category && entry.config.category !== filter.category) return false;
      if (filter.riskLevel && entry.config.riskLevel !== filter.riskLevel) return false;
      if (filter.source && entry.source !== filter.source) return false;
      return true;
    });
  }

  /** List all tool names */
  listNames(): string[] {
    return Array.from(this.tools.keys());
  }

  /** List tools as MCP tool definitions (for tools/list method) */
  listMcpDefinitions(): Array<{ name: string; description: string; inputSchema?: Record<string, unknown> }> {
    return this.list().map((entry) => ({
      name: entry.config.name,
      description: entry.config.description ?? entry.config.displayName ?? entry.config.name,
      inputSchema: entry.config.inputSchema as Record<string, unknown> | undefined,
    }));
  }

  /** Execute a tool by name with the given arguments */
  async execute(
    name: string,
    args: Record<string, unknown>,
    context: SdkExecutionContext,
  ): Promise<SdkToolResult> {
    const tool = this.tools.get(name);
    if (!tool) {
      return { success: false, error: `Tool "${name}" not found in registry` };
    }

    if (!tool.config.handler) {
      return { success: false, error: `Tool "${name}" has no execution handler` };
    }

    const start = Date.now();
    try {
      const result = await tool.config.handler(args, context);
      return { ...result, duration: result.duration ?? (Date.now() - start) };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : "Tool execution failed",
        duration: Date.now() - start,
      };
    }
  }

  /** Get the number of registered tools */
  get size(): number {
    return this.tools.size;
  }

  /** Alias for size (backward compat) */
  get count(): number {
    return this.tools.size;
  }
}
