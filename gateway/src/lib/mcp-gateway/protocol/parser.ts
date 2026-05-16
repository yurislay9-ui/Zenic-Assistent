// ─── Zenic-Agents v3 — MCP Protocol Layer: JSON-RPC 2.0 Parser ────────
// Single responsibility: Parse, validate, and construct JSON-RPC 2.0 messages

import type {
  JsonRpcRequest,
  JsonRpcResponse,
  JsonRpcSuccessResponse,
  JsonRpcErrorResponse,
  JsonRpcError,
} from "./types";

import { JSON_RPC_ERRORS } from "./types";

// ─── Parsing & Validation ────────────────────────────────

/** Result of parsing a raw value as a JSON-RPC 2.0 request */
export type ParseResult =
  | { ok: true; request: JsonRpcRequest }
  | { ok: false; error: JsonRpcError };

/**
 * Parse and validate a raw value as a JSON-RPC 2.0 request.
 *
 * Performs structural validation per the JSON-RPC 2.0 spec:
 * - Must be a non-null, non-array object
 * - `jsonrpc` must be the literal string `"2.0"`
 * - `method` must be a non-empty string
 * - `id` is optional; if present, must be string | number | null
 * - `params` is optional; if present, must be a plain object (not array)
 */
export function parseJsonRpcRequest(raw: unknown): ParseResult {
  // Must be a plain object (not null, not array)
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { ok: false, error: { ...JSON_RPC_ERRORS.INVALID_REQUEST } };
  }

  const obj = raw as Record<string, unknown>;

  // jsonrpc must be exactly "2.0"
  if (obj.jsonrpc !== "2.0") {
    return { ok: false, error: { ...JSON_RPC_ERRORS.INVALID_REQUEST } };
  }

  // method must be a non-empty string
  if (typeof obj.method !== "string" || obj.method.length === 0) {
    return { ok: false, error: { ...JSON_RPC_ERRORS.INVALID_REQUEST } };
  }

  // id is optional; if present, must be string | number | null
  if ("id" in obj && obj.id !== null && typeof obj.id !== "string" && typeof obj.id !== "number") {
    return { ok: false, error: { ...JSON_RPC_ERRORS.INVALID_REQUEST } };
  }

  // params is optional; if present, must be a plain object (not array)
  if (
    "params" in obj &&
    (typeof obj.params !== "object" || obj.params === null || Array.isArray(obj.params))
  ) {
    return { ok: false, error: { ...JSON_RPC_ERRORS.INVALID_PARAMS } };
  }

  return {
    ok: true,
    request: {
      jsonrpc: "2.0",
      id: (obj.id as string | number | null) ?? null,
      method: obj.method as string,
      params: (obj.params as Record<string, unknown>) ?? {},
    },
  };
}

// ─── Response Constructors ───────────────────────────────

/**
 * Create a JSON-RPC 2.0 success response.
 *
 * @param id - Matches the request id
 * @param result - The successful result payload
 */
export function successResponse(
  id: string | number | null,
  result: unknown
): JsonRpcSuccessResponse {
  return { jsonrpc: "2.0", id, result };
}

/**
 * Create a JSON-RPC 2.0 error response.
 *
 * @param id - Matches the request id (null if unparseable)
 * @param error - The error object with code, message, and optional data
 */
export function errorResponse(
  id: string | number | null,
  error: JsonRpcError
): JsonRpcErrorResponse {
  return { jsonrpc: "2.0", id, error };
}

// ─── Notification Constructor ────────────────────────────

/**
 * Create a JSON-RPC 2.0 notification (no id field — no response expected).
 *
 * @param method - The notification method name
 * @param params - Optional parameters
 */
export function notification(
  method: string,
  params?: Record<string, unknown>
): JsonRpcRequest {
  return { jsonrpc: "2.0", method, params };
}

// ─── Type Guards ─────────────────────────────────────────

/**
 * Type guard: returns true if the response is a JSON-RPC error response.
 */
export function isErrorResponse(
  response: JsonRpcResponse
): response is JsonRpcErrorResponse {
  return "error" in response;
}

/**
 * Type guard: returns true if the response is a JSON-RPC success response.
 */
export function isSuccessResponse(
  response: JsonRpcResponse
): response is JsonRpcSuccessResponse {
  return "result" in response;
}

/**
 * Type guard: returns true if the request is a notification (no id).
 * Notifications do not expect a response per the JSON-RPC 2.0 spec.
 */
export function isNotification(request: JsonRpcRequest): boolean {
  return !("id" in request) || request.id === undefined;
}
