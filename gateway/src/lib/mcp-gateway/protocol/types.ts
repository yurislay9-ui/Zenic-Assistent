// ─── Zenic-Agents v3 — MCP Protocol Layer: Type Definitions ──────────
// JSON-RPC 2.0 base types + MCP (Model Context Protocol) standard types
// Single responsibility: Pure type definitions and protocol constants

// ─── JSON-RPC 2.0 Base Types ──────────────────────────────

/** JSON-RPC 2.0 request */
export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number | null;
  method: string;
  params?: Record<string, unknown>;
}

/** JSON-RPC 2.0 success response */
export interface JsonRpcSuccessResponse {
  jsonrpc: "2.0";
  id: string | number | null;
  result: unknown;
}

/** JSON-RPC 2.0 error response */
export interface JsonRpcErrorResponse {
  jsonrpc: "2.0";
  id: string | number | null;
  error: JsonRpcError;
}

/** JSON-RPC 2.0 error object */
export interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
}

/** Union type for any JSON-RPC 2.0 response */
export type JsonRpcResponse = JsonRpcSuccessResponse | JsonRpcErrorResponse;

// ─── MCP Protocol Types ──────────────────────────────

/** MCP method names — all supported RPC methods */
export const MCP_METHODS = {
  INITIALIZE: "initialize",
  TOOLS_LIST: "tools/list",
  TOOLS_CALL: "tools/call",
  TOOLS_REGISTER: "tools/register",
  RESOURCES_LIST: "resources/list",
  RESOURCES_READ: "resources/read",
  PROMPTS_LIST: "prompts/list",
  PROMPTS_GET: "prompts/get",
  NOTIFICATION: "notifications/progress",
  CANCEL: "cancelled",
} as const;

/** MCP method string literal type */
export type McpMethod = (typeof MCP_METHODS)[keyof typeof MCP_METHODS];

// ─── MCP Initialize ──────────────────────────────

/** MCP initialize request params — sent by client on connect */
export interface McpInitializeParams {
  protocolVersion: string;
  capabilities: McpClientCapabilities;
  clientInfo: McpClientInfo;
}

/** Client capabilities declared during initialization */
export interface McpClientCapabilities {
  tools?: { listChanged?: boolean };
  resources?: { subscribe?: boolean; listChanged?: boolean };
  prompts?: { listChanged?: boolean };
  sampling?: Record<string, unknown>;
}

/** Client identity information */
export interface McpClientInfo {
  name: string;
  version: string;
}

// ─── MCP Server Info (our response) ──────────────────────

/** Server identity returned in initialize response */
export interface McpServerInfo {
  name: string;
  version: string;
}

/** Server capabilities returned in initialize response */
export interface McpServerCapabilities {
  tools?: { listChanged?: boolean };
  resources?: { subscribe?: boolean; listChanged?: boolean };
  prompts?: { listChanged?: boolean };
}

// ─── MCP Tools ──────────────────────────────

/** MCP tool definition — describes a tool's schema and metadata */
export interface McpToolDefinition {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, McpToolProperty>;
    required?: string[];
  };
  annotations?: McpToolAnnotations;
}

/** A single property in a tool's input schema */
export interface McpToolProperty {
  type: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  items?: McpToolProperty;
}

/** Tool annotations — behavioral hints for consumers */
export interface McpToolAnnotations {
  title?: string;
  readOnlyHint?: boolean;
  destructiveHint?: boolean;
  idempotentHint?: boolean;
  openWorldHint?: boolean;
}

// ─── MCP Tool Call ──────────────────────────────

/** MCP tool call request params */
export interface McpToolCallParams {
  name: string;
  arguments: Record<string, unknown>;
  /** Internal: tenant context injected by the gateway */
  _meta?: {
    tenantId?: string;
    traceId?: string;
    executorId?: string;
  };
}

/** MCP tool call result — the execution output */
export interface McpToolCallResult {
  content: McpContent[];
  isError?: boolean;
  /** Internal: gateway execution metadata */
  _meta?: {
    executionId?: string;
    verdict?: string;
    duration?: number;
  };
}

/** MCP content block — a single piece of output content */
export interface McpContent {
  type: "text" | "image" | "resource";
  text?: string;
  data?: string;
  mimeType?: string;
  resource?: {
    uri: string;
    mimeType?: string;
    text?: string;
  };
}

// ─── MCP Tool Registration ──────────────────────────────

/** MCP tool registration params — bulk registration of tools */
export interface McpToolRegistrationParams {
  tools: McpToolRegistrationEntry[];
}

/** A single tool entry in a registration request */
export interface McpToolRegistrationEntry {
  name: string;
  description: string;
  inputSchema: McpToolDefinition["inputSchema"];
  annotations?: McpToolAnnotations;
  permissions?: string[];
  rateLimit?: number;
  category?: string;
  riskLevel?: string;
  endpoint?: string;
  method?: string;
}

// ─── JSON-RPC Error Codes ──────────────────────────────

/** Standard JSON-RPC 2.0 error codes + MCP-specific extensions */
export const JSON_RPC_ERRORS = {
  // Standard JSON-RPC 2.0 errors
  PARSE_ERROR: { code: -32700, message: "Parse error" },
  INVALID_REQUEST: { code: -32600, message: "Invalid request" },
  METHOD_NOT_FOUND: { code: -32601, message: "Method not found" },
  INVALID_PARAMS: { code: -32602, message: "Invalid params" },
  INTERNAL_ERROR: { code: -32603, message: "Internal error" },
  // MCP-specific error codes (-32000 to -32099 range)
  TOOL_NOT_FOUND: { code: -32001, message: "Tool not found" },
  TOOL_EXECUTION_ERROR: { code: -32002, message: "Tool execution error" },
  PERMISSION_DENIED: { code: -32003, message: "Permission denied" },
  RATE_LIMIT_EXCEEDED: { code: -32004, message: "Rate limit exceeded" },
  AUTH_REQUIRED: { code: -32005, message: "Authentication required" },
  APPROVAL_REQUIRED: { code: -32006, message: "Approval required" },
  VALIDATION_ERROR: { code: -32007, message: "Validation error" },
} as const;

// ─── MCP Protocol Version ──────────────────────────────

/** Supported MCP protocol version */
export const MCP_PROTOCOL_VERSION = "2024-11-05";

/** Zenic Gateway software version */
export const ZENIC_GATEWAY_VERSION = "3.0.0";
