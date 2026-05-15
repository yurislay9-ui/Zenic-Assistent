// ─── Zenic-Agents MCP Gateway — Auth Type System ─────────────────────
// Registry Pattern: API keys and tenants held in-memory maps
// All in-memory for hot-path performance (no DB)

/** Authentication method */
export type AuthMethod = "api_key" | "bearer_token" | "mtls" | "none";

/** Authentication result */
export interface AuthResult {
  /** Whether authentication succeeded */
  authenticated: boolean;
  /** Which method was used */
  method: AuthMethod;
  /** Tenant ID extracted from the credential */
  tenantId?: string;
  /** Executor (agent/service) ID */
  executorId?: string;
  /** Roles granted to the authenticated identity */
  roles?: string[];
  /** Human-readable error when authenticated=false */
  error?: string;
  /** Token/API key metadata */
  metadata?: {
    /** Epoch ms when the credential was issued */
    issuedAt?: number;
    /** Epoch ms when the credential expires */
    expiresAt?: number;
    /** Permission scopes attached to the credential */
    scopes?: string[];
  };
}

/** API Key configuration — stored in the registry */
export interface ApiKeyConfig {
  /** The raw API key string */
  key: string;
  /** Tenant this key belongs to */
  tenantId: string;
  /** Human-readable name for the key */
  name: string;
  /** Permission scopes granted by this key */
  scopes: string[];
  /** Epoch ms when the key expires (undefined = never) */
  expiresAt?: number;
  /** Optional per-key rate-limit override (max RPM) */
  rateLimitOverride?: number;
}

/** Bearer token payload — decoded JWT-like structure */
export interface BearerTokenPayload {
  /** Subject — executor ID */
  sub: string;
  /** Tenant ID */
  tenantId: string;
  /** Roles assigned to this token */
  roles: string[];
  /** Permission scopes */
  scopes: string[];
  /** Issued-at (epoch seconds) */
  iat: number;
  /** Expiration (epoch seconds) */
  exp: number;
}

/** Tenant configuration — stored in the registry */
export interface TenantConfig {
  /** Unique tenant identifier */
  id: string;
  /** Human-readable tenant name */
  name: string;
  /** Permissions granted to this tenant */
  permissions: string[];
  /** Per-tool rate limits: toolName → max RPM */
  rateLimits: Record<string, number>;
  /** Whether the tenant is currently enabled */
  enabled: boolean;
}

/** Authentication headers — extracted from an HTTP request */
export interface AuthHeaders {
  /** X-API-Key header value */
  "x-api-key"?: string;
  /** Authorization header value (Bearer / ApiKey / etc.) */
  authorization?: string;
}
