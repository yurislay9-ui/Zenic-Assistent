// ─── Zenic-Agents v3 — Native Executor Adapter ──────────────────────
// Registers the 19 existing Zenic executor types as MCP tools.
// Each executor gets a proper inputSchema, permissions, and risk level.
//
// Pattern: Adapter Pattern — converts native executor definitions to SDK tools.
// Pattern: Factory Pattern — handlerFactory creates per-executor handlers.

import { getRegistry } from "../sdk/sdk";
import type {
  SdkToolConfig,
  SdkExecutionContext,
  SdkToolResult,
} from "../sdk/types";

// ─── Executor Types ──────────────────────────────────────────────────

/** Zenic executor types (from the original repo) */
export const ZENIC_EXECUTOR_TYPES = [
  "http_request",
  "database_query",
  "file_operation",
  "email_send",
  "webhook_dispatch",
  "cache_operation",
  "queue_publish",
  "search_query",
  "transform_data",
  "validate_schema",
  "encrypt_decrypt",
  "log_write",
  "notification_send",
  "schedule_task",
  "compute_execute",
  "storage_operation",
  "api_gateway",
  "rate_limit_check",
  "audit_record",
] as const;

export type ZenicExecutorType =
  (typeof ZENIC_EXECUTOR_TYPES)[keyof typeof ZENIC_EXECUTOR_TYPES];

// ─── Executor Schema Definitions ─────────────────────────────────────

/** Schema definition for a single executor type */
interface ExecutorSchemaDef {
  inputSchema: SdkToolConfig["inputSchema"];
  riskLevel: SdkToolConfig["riskLevel"];
  category: string;
  permissions: string[];
  description: string;
}

const EXECUTOR_SCHEMAS: Record<ZenicExecutorType, ExecutorSchemaDef> = {
  http_request: {
    description: "Execute HTTP requests to external APIs and services",
    category: "communication",
    riskLevel: "medium",
    permissions: ["http:execute"],
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "Target URL" },
        method: {
          type: "string",
          description: "HTTP method",
          enum: ["GET", "POST", "PUT", "DELETE", "PATCH"],
        },
        headers: { type: "object", description: "Request headers" },
        body: { type: "object", description: "Request body" },
      },
      required: ["url", "method"],
    },
  },
  database_query: {
    description: "Execute database queries with connection management",
    category: "data",
    riskLevel: "high",
    permissions: ["database:query"],
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "SQL query to execute" },
        connectionId: {
          type: "string",
          description: "Database connection identifier",
        },
        params: { type: "object", description: "Query parameters" },
      },
      required: ["query", "connectionId"],
    },
  },
  file_operation: {
    description: "Read, write, and manage file operations",
    category: "storage",
    riskLevel: "medium",
    permissions: ["file:read", "file:write"],
    inputSchema: {
      type: "object",
      properties: {
        operation: {
          type: "string",
          description: "File operation",
          enum: ["read", "write", "delete", "list", "move"],
        },
        path: { type: "string", description: "File path" },
        content: { type: "string", description: "File content (for write)" },
      },
      required: ["operation", "path"],
    },
  },
  email_send: {
    description: "Send emails with template support and delivery tracking",
    category: "communication",
    riskLevel: "high",
    permissions: ["email:send"],
    inputSchema: {
      type: "object",
      properties: {
        to: {
          type: "array",
          description: "Recipient emails",
          items: { type: "string" },
        },
        subject: { type: "string", description: "Email subject" },
        body: { type: "string", description: "Email body" },
        template: { type: "string", description: "Template name" },
      },
      required: ["to", "subject"],
    },
  },
  webhook_dispatch: {
    description: "Dispatch webhook events to registered endpoints",
    category: "communication",
    riskLevel: "medium",
    permissions: ["webhook:dispatch"],
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "Webhook URL" },
        event: { type: "string", description: "Event type" },
        payload: { type: "object", description: "Event payload" },
      },
      required: ["url", "event", "payload"],
    },
  },
  cache_operation: {
    description: "Manage cache entries with TTL support",
    category: "compute",
    riskLevel: "low",
    permissions: ["cache:manage"],
    inputSchema: {
      type: "object",
      properties: {
        operation: {
          type: "string",
          enum: ["get", "set", "delete", "invalidate"],
        },
        key: { type: "string" },
        value: { type: "string" },
        ttl: { type: "number", description: "TTL in seconds" },
      },
      required: ["operation", "key"],
    },
  },
  queue_publish: {
    description: "Publish messages to message queues",
    category: "communication",
    riskLevel: "medium",
    permissions: ["queue:publish"],
    inputSchema: {
      type: "object",
      properties: {
        queue: { type: "string", description: "Queue name" },
        message: { type: "object", description: "Message payload" },
        priority: {
          type: "string",
          enum: ["low", "normal", "high"],
        },
      },
      required: ["queue", "message"],
    },
  },
  search_query: {
    description: "Execute search queries against indexed data",
    category: "data",
    riskLevel: "low",
    permissions: ["search:query"],
    inputSchema: {
      type: "object",
      properties: {
        index: { type: "string", description: "Search index" },
        query: { type: "string", description: "Search query" },
        limit: { type: "number", description: "Max results" },
      },
      required: ["index", "query"],
    },
  },
  transform_data: {
    description: "Transform data between formats and schemas",
    category: "data",
    riskLevel: "low",
    permissions: ["data:transform"],
    inputSchema: {
      type: "object",
      properties: {
        input: { type: "object", description: "Input data" },
        transform: { type: "string", description: "Transform type" },
        format: { type: "string", description: "Output format" },
      },
      required: ["input", "transform"],
    },
  },
  validate_schema: {
    description: "Validate data against JSON schemas",
    category: "data",
    riskLevel: "low",
    permissions: ["schema:validate"],
    inputSchema: {
      type: "object",
      properties: {
        data: { type: "object", description: "Data to validate" },
        schema: { type: "object", description: "JSON Schema" },
      },
      required: ["data", "schema"],
    },
  },
  encrypt_decrypt: {
    description: "Encrypt and decrypt sensitive data with key management",
    category: "security",
    riskLevel: "critical",
    permissions: ["crypto:manage"],
    inputSchema: {
      type: "object",
      properties: {
        operation: {
          type: "string",
          enum: ["encrypt", "decrypt", "hash", "sign", "verify"],
        },
        data: { type: "string", description: "Data to process" },
        keyId: { type: "string", description: "Key identifier" },
      },
      required: ["operation", "data"],
    },
  },
  log_write: {
    description: "Write structured log entries",
    category: "monitoring",
    riskLevel: "low",
    permissions: ["log:write"],
    inputSchema: {
      type: "object",
      properties: {
        level: {
          type: "string",
          enum: ["debug", "info", "warn", "error"],
        },
        message: { type: "string" },
        metadata: { type: "object" },
      },
      required: ["level", "message"],
    },
  },
  notification_send: {
    description: "Send notifications across multiple channels",
    category: "communication",
    riskLevel: "low",
    permissions: ["notification:send"],
    inputSchema: {
      type: "object",
      properties: {
        channel: {
          type: "string",
          enum: ["email", "sms", "push", "slack", "webhook"],
        },
        recipient: { type: "string" },
        message: { type: "string" },
      },
      required: ["channel", "recipient", "message"],
    },
  },
  schedule_task: {
    description: "Schedule tasks for future execution",
    category: "compute",
    riskLevel: "medium",
    permissions: ["task:schedule"],
    inputSchema: {
      type: "object",
      properties: {
        taskType: { type: "string" },
        schedule: {
          type: "string",
          description: "Cron expression or ISO timestamp",
        },
        params: { type: "object" },
      },
      required: ["taskType", "schedule"],
    },
  },
  compute_execute: {
    description:
      "Execute compute tasks including ML inference and batch operations",
    category: "compute",
    riskLevel: "high",
    permissions: ["compute:execute"],
    inputSchema: {
      type: "object",
      properties: {
        taskType: {
          type: "string",
          enum: ["data_processing", "ml_inference", "batch", "script"],
        },
        payload: { type: "object" },
        timeout: { type: "number" },
      },
      required: ["taskType", "payload"],
    },
  },
  storage_operation: {
    description: "Cloud storage operations (S3, GCS, Azure Blob)",
    category: "storage",
    riskLevel: "medium",
    permissions: ["storage:manage"],
    inputSchema: {
      type: "object",
      properties: {
        operation: {
          type: "string",
          enum: ["upload", "download", "delete", "list", "copy"],
        },
        bucket: { type: "string" },
        key: { type: "string" },
      },
      required: ["operation", "bucket"],
    },
  },
  api_gateway: {
    description:
      "Route requests through API gateway with rate limiting and auth",
    category: "external",
    riskLevel: "medium",
    permissions: ["gateway:route"],
    inputSchema: {
      type: "object",
      properties: {
        service: { type: "string" },
        endpoint: { type: "string" },
        method: { type: "string" },
        payload: { type: "object" },
      },
      required: ["service", "endpoint"],
    },
  },
  rate_limit_check: {
    description: "Check rate limit status for a tool/tenant",
    category: "monitoring",
    riskLevel: "low",
    permissions: ["ratelimit:check"],
    inputSchema: {
      type: "object",
      properties: {
        toolName: { type: "string" },
        tenantId: { type: "string" },
      },
      required: ["toolName"],
    },
  },
  audit_record: {
    description: "Record audit entries in the Merkle ledger",
    category: "security",
    riskLevel: "low",
    permissions: ["audit:write"],
    inputSchema: {
      type: "object",
      properties: {
        action: { type: "string" },
        resource: { type: "string" },
        outcome: {
          type: "string",
          enum: ["success", "failure", "denied"],
        },
        details: { type: "object" },
      },
      required: ["action", "resource"],
    },
  },
};

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
