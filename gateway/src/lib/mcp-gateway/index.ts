// ─── Zenic-Agents v3 — MCP Gateway Barrel Export ─────────────────
// Public API — import anything from '@/lib/mcp-gateway'

// Protocol
export { MCP_METHODS, MCP_PROTOCOL_VERSION, ZENIC_GATEWAY_VERSION, JSON_RPC_ERRORS } from "./protocol/types";
export { parseJsonRpcRequest, successResponse, errorResponse, notification, isErrorResponse } from "./protocol/parser";
export type { JsonRpcRequest, JsonRpcSuccessResponse, JsonRpcErrorResponse, JsonRpcError, JsonRpcResponse, McpMethod, McpInitializeParams, McpClientCapabilities, McpClientInfo, McpServerInfo, McpServerCapabilities, McpToolDefinition, McpToolProperty, McpToolAnnotations, McpToolCallParams, McpToolCallResult, McpContent, McpToolRegistrationParams, McpToolRegistrationEntry } from "./protocol/types";

// Auth
export { AuthService } from "./auth/auth-service";
export type { AuthMethod, AuthResult, ApiKeyConfig, BearerTokenPayload, TenantConfig } from "./auth/types";

// Rate Limiter
export { RateLimiter } from "./rate-limiter/rate-limiter";
export type { RateLimitAlgorithm, RateLimitConfig, RateLimitResult, RateLimitKey } from "./rate-limiter/types";

// SDK
export { mcpTool, getRegistry, resetRegistry } from "./sdk/sdk";
export { ToolRegistry } from "./sdk/tool-registry";
export type { SdkToolConfig, SdkToolHandler, SdkExecutionContext, SdkToolResult, SdkToolRegistryEntry } from "./sdk/types";

// Adapters
export { registerOpenAITool, registerOpenAITools } from "./adapters/openai-adapter";
export { registerNativeExecutors, ZENIC_EXECUTOR_TYPES } from "./adapters/native-adapter";
export type { OpenAIFunction, OpenAITool } from "./adapters/openai-adapter";
export type { ZenicExecutorType } from "./adapters/native-adapter";

// Audit
export { MerkleAuditService } from "./audit/merkle-audit";
export type { AuditEntry, MerkleVerificationResult, AuditQueryParams } from "./audit/types";

// Engine
export { GatewayEngine } from "./engine/gateway-engine";
export { ObservableGatewayEngine } from "./engine/observable-engine";
export type { GatewayRequest, GatewayResponse, GatewayPipelineStep, GatewayConfig } from "./engine/types";

// Bootstrap
export { initializeGateway, resetGateway, getAuditService, getObservableGateway, initializeObservability } from "./bootstrap";

// Shared types (backward compat)
export * from "./types";
