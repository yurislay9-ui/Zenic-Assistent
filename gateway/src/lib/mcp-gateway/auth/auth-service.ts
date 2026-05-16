// ─── Zenic-Agents MCP Gateway — Auth Service ────────────────────────
// Registry Pattern: API keys and tenants held in-memory maps
// All in-memory for hot-path performance (no DB)

import {
  AuthResult,
  ApiKeyConfig,
  TenantConfig,
  BearerTokenPayload,
} from "./types";

/**
 * In-memory authentication service for the MCP Gateway.
 *
 * Supports two authentication methods:
 *
 * 1. **API Key** — supplied via `X-API-Key` header or
 *    `Authorization: ApiKey <key>`. Keys are looked up in an in-memory
 *    registry and checked for expiry + tenant status.
 *
 * 2. **Bearer Token** — supplied via `Authorization: Bearer <token>`.
 *    Tokens are expected to be base64-encoded JSON (JWT-like, simplified).
 *    Falls back to API-key lookup if decoding fails.
 */
export class AuthService {
  private apiKeys = new Map<string, ApiKeyConfig>();
  private tenants = new Map<string, TenantConfig>();

  // ─── Registry Operations ──────────────────────────────────────────

  /** Register an API key in the registry */
  registerApiKey(config: ApiKeyConfig): void {
    this.apiKeys.set(config.key, config);

    // Auto-register tenant if not already present
    if (!this.tenants.has(config.tenantId)) {
      this.tenants.set(config.tenantId, {
        id: config.tenantId,
        name: config.tenantId,
        permissions: [...config.scopes],
        rateLimits: {},
        enabled: true,
      });
    }
  }

  /** Remove an API key from the registry */
  unregisterApiKey(key: string): boolean {
    return this.apiKeys.delete(key);
  }

  /** Register a tenant configuration */
  registerTenant(config: TenantConfig): void {
    this.tenants.set(config.id, config);
  }

  /** Remove a tenant from the registry */
  unregisterTenant(tenantId: string): boolean {
    return this.tenants.delete(tenantId);
  }

  /** Enable or disable a tenant */
  setTenantEnabled(tenantId: string, enabled: boolean): boolean {
    const tenant = this.tenants.get(tenantId);
    if (!tenant) return false;
    tenant.enabled = enabled;
    return true;
  }

  // ─── Authentication ───────────────────────────────────────────────

  /** Authenticate a request from its headers */
  authenticate(headers: Record<string, string | undefined>): AuthResult {
    // 1. Check for API key in X-API-Key header
    const xApiKey = headers["x-api-key"];
    if (xApiKey) {
      return this.authenticateApiKey(xApiKey);
    }

    // 2. Check Authorization header
    const authHeader = headers["authorization"];
    if (authHeader) {
      // ApiKey scheme
      if (authHeader.startsWith("ApiKey ")) {
        return this.authenticateApiKey(authHeader.slice(7));
      }

      // Bearer scheme
      if (authHeader.startsWith("Bearer ")) {
        const token = authHeader.slice(7);
        return this.authenticateBearerToken(token);
      }
    }

    // 3. No auth provided
    return {
      authenticated: false,
      method: "none",
      error:
        "No authentication provided. Use X-API-Key or Authorization: Bearer <token>",
    };
  }

  /** Authenticate using an API key */
  private authenticateApiKey(key: string): AuthResult {
    const config = this.apiKeys.get(key);
    if (!config) {
      return {
        authenticated: false,
        method: "api_key",
        error: "Invalid API key",
      };
    }

    // Check expiry
    if (config.expiresAt && Date.now() > config.expiresAt) {
      return {
        authenticated: false,
        method: "api_key",
        error: "API key expired",
      };
    }

    // Check tenant status
    const tenant = this.tenants.get(config.tenantId);
    if (!tenant) {
      return {
        authenticated: false,
        method: "api_key",
        error: "Tenant not found",
      };
    }
    if (!tenant.enabled) {
      return {
        authenticated: false,
        method: "api_key",
        error: "Tenant is disabled",
      };
    }

    return {
      authenticated: true,
      method: "api_key",
      tenantId: config.tenantId,
      executorId: config.name,
      roles: tenant.permissions,
      metadata: {
        scopes: config.scopes,
        expiresAt: config.expiresAt,
      },
    };
  }

  /** Authenticate using a bearer token (base64-encoded JSON, simplified JWT) */
  private authenticateBearerToken(token: string): AuthResult {
    // In production this would verify a JWT signature with a signing key.
    // For this implementation we decode base64-encoded JSON payloads.
    try {
      const decoded = this.decodeBearerPayload(token);

      if (!decoded.sub || !decoded.tenantId) {
        return {
          authenticated: false,
          method: "bearer_token",
          error: "Invalid token: missing sub or tenantId",
        };
      }

      // Check tenant status
      const tenant = this.tenants.get(decoded.tenantId);
      if (!tenant) {
        return {
          authenticated: false,
          method: "bearer_token",
          error: "Tenant not found",
        };
      }
      if (!tenant.enabled) {
        return {
          authenticated: false,
          method: "bearer_token",
          error: "Tenant is disabled",
        };
      }

      // Check expiration
      if (decoded.exp && Date.now() / 1000 > decoded.exp) {
        return {
          authenticated: false,
          method: "bearer_token",
          error: "Token expired",
        };
      }

      return {
        authenticated: true,
        method: "bearer_token",
        tenantId: decoded.tenantId,
        executorId: decoded.sub,
        roles: decoded.roles ?? tenant.permissions,
        metadata: {
          issuedAt: decoded.iat ? decoded.iat * 1000 : undefined,
          expiresAt: decoded.exp ? decoded.exp * 1000 : undefined,
          scopes: decoded.scopes ?? [],
        },
      };
    } catch {
      // Not valid base64 JSON — try as an API key alias for convenience
      return this.authenticateApiKey(token);
    }
  }

  /**
   * Decode a bearer token payload from base64-encoded JSON.
   * Handles both raw base64 and "header.payload.signature" JWT-like format
   * by extracting the payload segment.
   */
  private decodeBearerPayload(token: string): BearerTokenPayload {
    // If the token looks like a JWT (two or more dots), extract the payload
    const segments = token.split(".");
    const payloadSegment =
      segments.length >= 2 ? segments[1] : segments[0];

    const jsonStr = Buffer.from(payloadSegment, "base64").toString("utf-8");
    return JSON.parse(jsonStr) as BearerTokenPayload;
  }

  // ─── Authorization Helpers ────────────────────────────────────────

  /** Check if a tenant has a specific permission (supports wildcard "*") */
  hasPermission(tenantId: string, permission: string): boolean {
    const tenant = this.tenants.get(tenantId);
    if (!tenant) return false;
    return (
      tenant.permissions.includes(permission) ||
      tenant.permissions.includes("*")
    );
  }

  /** Check if a tenant has ALL of the specified permissions */
  hasAllPermissions(tenantId: string, permissions: string[]): boolean {
    return permissions.every((p) => this.hasPermission(tenantId, p));
  }

  /** Check if a tenant has ANY of the specified permissions */
  hasAnyPermission(tenantId: string, permissions: string[]): boolean {
    return permissions.some((p) => this.hasPermission(tenantId, p));
  }

  // ─── Lookup Helpers ───────────────────────────────────────────────

  /** Get tenant configuration */
  getTenant(tenantId: string): TenantConfig | undefined {
    return this.tenants.get(tenantId);
  }

  /** Get all registered tenant IDs */
  getTenantIds(): string[] {
    return Array.from(this.tenants.keys());
  }

  /** Get API key config by key value (for admin UI) */
  getApiKeyConfig(key: string): ApiKeyConfig | undefined {
    return this.apiKeys.get(key);
  }

  /** List API key configs for a given tenant */
  listApiKeysForTenant(tenantId: string): ApiKeyConfig[] {
    const result: ApiKeyConfig[] = [];
    for (const config of this.apiKeys.values()) {
      if (config.tenantId === tenantId) {
        result.push(config);
      }
    }
    return result;
  }

  // ─── Stats ────────────────────────────────────────────────────────

  /** Get registry stats for monitoring / debugging */
  getStats(): {
    registeredApiKeys: number;
    registeredTenants: number;
    activeTenants: number;
  } {
    let activeTenants = 0;
    for (const tenant of this.tenants.values()) {
      if (tenant.enabled) activeTenants++;
    }
    return {
      registeredApiKeys: this.apiKeys.size,
      registeredTenants: this.tenants.size,
      activeTenants,
    };
  }
}
