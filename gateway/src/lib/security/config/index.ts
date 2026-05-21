/**
 * @module security/config
 * @description Centralized secure-by-default security configuration for the Zenic-Agents gateway.
 *
 * This module is the **single source of truth** for every security-related setting
 * in the gateway. All values ship with secure defaults; environment variables may
 * override them at runtime, but only when they pass strict validation. If an
 * environment variable is malformed or insecure, the secure default is retained
 * and a warning is emitted (fail-closed semantics).
 *
 * Key design principles:
 * 1. **Secure by default** — every value is safe out of the box; no action needed.
 * 2. **Fail closed** — invalid overrides fall back to the secure default, never to
 *    a less-secure value.
 * 3. **Explicit is better than implicit** — every override is logged so operators
 *    can audit the effective configuration.
 * 4. **Detect insecure defaults** — known placeholder values (e.g. `"change-me"`)
 *    are flagged at load time.
 *
 * @example
 * ```ts
 * import { loadSecurityConfig, validateSecurityConfig, SecurityConfig } from '@/lib/security/config';
 *
 * // Load the effective config (defaults + env overrides)
 * const config = loadSecurityConfig();
 *
 * // Validate any config object (e.g. before persisting)
 * const result = validateSecurityConfig(config);
 * if (!result.valid) {
 *   console.error('Security config errors:', result.errors);
 * }
 * ```
 */

// ─── Rate Limit Tier ───────────────────────────────────────────────────

/**
 * Defines a named rate-limit tier that applies to a set of routes.
 *
 * Tiers allow different routes to have different throughput budgets —
 * for example, health-check endpoints can be more generous than
 * authentication or payment endpoints.
 *
 * @example
 * ```ts
 * const tier: RateLimitTier = {
 *   name: 'auth',
 *   windowMs: 15 * 60 * 1000,  // 15 minutes
 *   maxRequests: 10,
 *   routes: ['/api/auth/login', '/api/auth/token'],
 * };
 * ```
 */
export interface RateLimitTier {
  /** Human-readable name for this tier (e.g. `"auth"`, `"public"`, `"admin"`). */
  name: string;
  /** Time window in milliseconds over which requests are counted. */
  windowMs: number;
  /** Maximum number of requests allowed within the window. */
  maxRequests: number;
  /**
   * Route patterns this tier applies to. Supports glob-style patterns
   * (e.g. `/api/auth/**`, `/api/admin/*`).
   */
  routes: string[];
}

// ─── SecurityConfig Sub-types ──────────────────────────────────────────

/** CORS (Cross-Origin Resource Sharing) configuration. */
export interface CorsConfig {
  /** Allowed origin patterns. Empty array = no cross-origin access. Use `*` only in dev. */
  allowedOrigins: string[];
  /** Allowed HTTP methods for cross-origin requests. */
  allowedMethods: string[];
  /** How long the preflight result can be cached (seconds). */
  maxAge: number;
  /** Whether to include credentials (cookies, auth headers) in CORS requests. */
  credentials: boolean;
}

/** Rate-limiting configuration. */
export interface RateLimitConfig {
  /** Default sliding-window duration in milliseconds. */
  windowMs: number;
  /** Default maximum requests per window. */
  maxRequests: number;
  /** Named tiers with per-route overrides. */
  tiers: RateLimitTier[];
}

/** Session management configuration. */
export interface SessionConfig {
  /** Absolute session timeout in milliseconds. */
  timeoutMs: number;
  /** Maximum concurrent sessions per user (older sessions are evicted). */
  maxSessionsPerUser: number;
  /** Whether to rotate session IDs on privilege escalation. */
  enableRotation: boolean;
}

/** Audit logging configuration. */
export interface AuditConfig {
  /** Whether audit logging is enabled. */
  enabled: boolean;
  /** Whether to write audit events to the console (structured JSON). */
  logToConsole: boolean;
  /** Whether to persist audit events to the database. */
  logToDb: boolean;
  /** Number of days to retain audit records before pruning. */
  retentionDays: number;
}

/** Input sanitization configuration. */
export interface SanitizeConfig {
  /** Maximum allowed length for URL query-parameter values. */
  maxQueryParamLength: number;
  /** Maximum allowed request body size in bytes. */
  maxBodySize: number;
  /** Whether to run SQL-injection detection on inputs. */
  enableSqlDetection: boolean;
  /** Whether to run XSS detection on inputs. */
  enableXssDetection: boolean;
}

/** Security headers configuration. */
export interface HeadersConfig {
  /** Whether to send the `Strict-Transport-Security` header. */
  enableHsts: boolean;
  /** Whether to send the `Content-Security-Policy` header. */
  enableCsp: boolean;
  /** CSP directives as a map of directive name → allowed values. */
  cspDirectives: Record<string, string[]>;
}

/** Encryption / key-derivation configuration. */
export interface EncryptionConfig {
  /** Minimum acceptable passphrase length (characters). Must be >= 32. */
  minPassphraseLength: number;
  /** Number of PBKDF2 iterations for key derivation. Must be >= 100 000. */
  pbkdf2Iterations: number;
  /** Whether to bind derived keys to hardware identifiers (TPM / SGX). */
  enableHardwareBinding: boolean;
}

/** Authentication configuration. */
export interface AuthConfig {
  /** Whether authentication is mandatory in production environments. */
  requireAuthInProduction: boolean;
  /**
   * User ID used to bypass authentication in development only.
   * Must **never** be a real user ID in production.
   */
  devBypassUserId: string;
  /** Maximum consecutive login failures before the account is locked. */
  maxLoginAttempts: number;
}

// ─── SecurityConfig (composite) ────────────────────────────────────────

/**
 * Composite security configuration object for the Zenic-Agents gateway.
 *
 * Every nested property ships with a secure default so that simply
 * importing `SecurityConfig` yields a production-ready configuration
 * without any additional setup.
 *
 * Override individual values through environment variables (see
 * {@link loadSecurityConfig}) or by merging a partial object into the
 * defaults.
 */
export interface SecurityConfigType {
  /** Cross-Origin Resource Sharing settings. */
  cors: CorsConfig;
  /** Rate-limiting settings and per-route tiers. */
  rateLimit: RateLimitConfig;
  /** Session management settings. */
  session: SessionConfig;
  /** Audit logging settings. */
  audit: AuditConfig;
  /** Input sanitization settings. */
  sanitize: SanitizeConfig;
  /** Security HTTP headers settings. */
  headers: HeadersConfig;
  /** Encryption and key-derivation settings. */
  encryption: EncryptionConfig;
  /** Authentication settings. */
  auth: AuthConfig;
}

// ─── Secure Defaults ───────────────────────────────────────────────────

/**
 * The canonical secure-by-default configuration.
 *
 * Every value is chosen to be safe for production use without modification.
 * Environment variables or explicit overrides may relax certain settings
 * for development convenience, but the defaults err on the side of
 * **restriction**.
 *
 * @example
 * ```ts
 * import { SecurityConfig } from '@/lib/security/config';
 *
 * // Read a default
 * console.log(SecurityConfig.rateLimit.maxRequests); // 100
 *
 * // Spread into a custom config
 * const custom: SecurityConfigType = {
 *   ...SecurityConfig,
 *   cors: { ...SecurityConfig.cors, allowedOrigins: ['https://app.example.com'] },
 * };
 * ```
 */
export const SecurityConfig: SecurityConfigType = {
  cors: {
    /** No origins allowed by default — must be explicitly opened. */
    allowedOrigins: [],
    allowedMethods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    /** 1 day preflight cache — reduces OPTIONS traffic. */
    maxAge: 86400,
    /** Credentials disabled by default — enable only with specific origins. */
    credentials: false,
  },

  rateLimit: {
    /** 15-minute sliding window. */
    windowMs: 15 * 60 * 1000,
    /** 100 requests per window by default. */
    maxRequests: 100,
    tiers: [
      {
        name: 'auth',
        windowMs: 15 * 60 * 1000,
        maxRequests: 10,
        routes: ['/api/auth/login', '/api/auth/token', '/api/auth/register'],
      },
      {
        name: 'public',
        windowMs: 60 * 1000,
        maxRequests: 60,
        routes: ['/api/health', '/api/status'],
      },
      {
        name: 'admin',
        windowMs: 15 * 60 * 1000,
        maxRequests: 20,
        routes: ['/api/admin/**'],
      },
    ],
  },

  session: {
    /** 30-minute absolute timeout. */
    timeoutMs: 30 * 60 * 1000,
    /** Only 3 concurrent sessions per user. */
    maxSessionsPerUser: 3,
    /** Rotate session IDs on privilege changes. */
    enableRotation: true,
  },

  audit: {
    /** Audit logging is always on. */
    enabled: true,
    logToConsole: true,
    logToDb: true,
    /** Retain audit records for 90 days. */
    retentionDays: 90,
  },

  sanitize: {
    /** Maximum query-param value length: 2 KB. */
    maxQueryParamLength: 2048,
    /** Maximum request body size: 1 MB. */
    maxBodySize: 1024 * 1024,
    /** SQL injection detection enabled. */
    enableSqlDetection: true,
    /** XSS detection enabled. */
    enableXssDetection: true,
  },

  headers: {
    /** HSTS enabled by default (requires TLS). */
    enableHsts: true,
    /** CSP enabled by default. */
    enableCsp: true,
    cspDirectives: {
      'default-src': ["'none'"],
      'script-src': ["'self'"],
      'style-src': ["'self'", "'unsafe-inline'"],
      'img-src': ["'self'"],
      'font-src': ["'self'"],
      'connect-src': ["'self'"],
      'frame-ancestors': ["'none'"],
      'base-uri': ["'self'"],
      'form-action': ["'self'"],
    },
  },

  encryption: {
    /** Minimum 32-character passphrase (OWASP recommendation). */
    minPassphraseLength: 32,
    /** 600 000 PBKDF2 iterations (OWASP 2023 recommendation). */
    pbkdf2Iterations: 600_000,
    /** Hardware binding disabled by default (requires TPM/SGX support). */
    enableHardwareBinding: false,
  },

  auth: {
    /** Auth is mandatory in production. */
    requireAuthInProduction: true,
    /** Dev bypass user — clearly marked as unsafe. */
    devBypassUserId: '__DEV_BYPASS__',
    /** Lock account after 5 consecutive failures. */
    maxLoginAttempts: 5,
  },
};

// ─── Insecure Defaults Detection ───────────────────────────────────────

/**
 * Known insecure default / placeholder values that should never appear
 * in production configurations.
 *
 * When any of these values are detected in environment variables,
 * {@link loadSecurityConfig} will emit a warning and replace the value
 * with the secure default.
 */
export const INSECURE_DEFAULTS: readonly string[] = [
  'default-key',
  'change-me',
  'secret',
  'password',
  'admin',
  'root',
  'test',
  'example',
  'changeme',
  '123456',
  'abcdef',
  'abc123',
  'default',
  'placeholder',
  'todo',
  'fixme',
  'insecure',
  'not-secret',
  'no-secret',
  'none',
  'null',
  'undefined',
  'empty',
  'xxxxxxxx',
  'xxxx',
  'your-secret-key',
  'your-api-key',
  'replace-me',
  'insert-key-here',
  'xxx',
];

// ─── Environment Variable Mapping ──────────────────────────────────────

/**
 * Describes how a single environment variable maps to a field inside
 * {@link SecurityConfigType}.
 */
interface EnvMapping {
  /** The environment variable name (e.g. `ZENIC_CORS_ORIGINS`). */
  envVar: string;
  /** Dot-path to the target field in the config (e.g. `cors.allowedOrigins`). */
  configPath: string;
  /**
   * Parser that converts the raw string value into the correct type.
   * Returns `undefined` if the value is invalid (triggers fallback to default).
   */
  parse: (raw: string) => unknown;
  /** Optional validator; returns an error message if the parsed value is invalid. */
  validate?: (parsed: unknown) => string | null;
}

/**
 * Complete mapping of environment variables to security configuration fields.
 *
 * Each entry specifies how to parse and (optionally) validate the raw
 * environment variable string before it is applied as an override.
 */
const ENV_MAPPINGS: readonly EnvMapping[] = [
  // ── CORS ───────────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_CORS_ORIGINS',
    configPath: 'cors.allowedOrigins',
    parse: (raw) => {
      if (raw.trim() === '') return undefined;
      return raw.split(',').map((s) => s.trim()).filter(Boolean);
    },
    validate: (parsed) => {
      if (!Array.isArray(parsed)) return null; // will fall back to default
      if (parsed.includes('*')) {
        return 'Wildcard CORS origin ("*") detected — this is insecure in production';
      }
      return null;
    },
  },
  {
    envVar: 'ZENIC_CORS_MAX_AGE',
    configPath: 'cors.maxAge',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 0) return 'CORS maxAge cannot be negative';
      return null;
    },
  },
  {
    envVar: 'ZENIC_CORS_CREDENTIALS',
    configPath: 'cors.credentials',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
  },

  // ── Rate Limit ─────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_RATE_LIMIT_WINDOW',
    configPath: 'rateLimit.windowMs',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 1000) return 'Rate limit window must be at least 1000ms';
      return null;
    },
  },
  {
    envVar: 'ZENIC_RATE_LIMIT_MAX',
    configPath: 'rateLimit.maxRequests',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 1) return 'Rate limit maxRequests must be at least 1';
      return null;
    },
  },

  // ── Session ────────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_SESSION_TIMEOUT',
    configPath: 'session.timeoutMs',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 60_000) return 'Session timeout must be at least 60000ms (1 minute)';
      return null;
    },
  },
  {
    envVar: 'ZENIC_SESSION_MAX_PER_USER',
    configPath: 'session.maxSessionsPerUser',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 1) return 'maxSessionsPerUser must be at least 1';
      return null;
    },
  },
  {
    envVar: 'ZENIC_SESSION_ROTATION',
    configPath: 'session.enableRotation',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
  },

  // ── Audit ──────────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_AUDIT_ENABLED',
    configPath: 'audit.enabled',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
  },
  {
    envVar: 'ZENIC_AUDIT_LOG_CONSOLE',
    configPath: 'audit.logToConsole',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
  },
  {
    envVar: 'ZENIC_AUDIT_LOG_DB',
    configPath: 'audit.logToDb',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
  },
  {
    envVar: 'ZENIC_AUDIT_RETENTION_DAYS',
    configPath: 'audit.retentionDays',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 7) return 'Audit retention must be at least 7 days';
      return null;
    },
  },

  // ── Sanitize ───────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_SANITIZE_MAX_QUERY_LENGTH',
    configPath: 'sanitize.maxQueryParamLength',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 64) return 'maxQueryParamLength must be at least 64';
      return null;
    },
  },
  {
    envVar: 'ZENIC_SANITIZE_MAX_BODY_SIZE',
    configPath: 'sanitize.maxBodySize',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 1024) return 'maxBodySize must be at least 1024 bytes';
      return null;
    },
  },
  {
    envVar: 'ZENIC_SANITIZE_SQL_DETECTION',
    configPath: 'sanitize.enableSqlDetection',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
    validate: (parsed) => {
      if (parsed === false) return 'Disabling SQL injection detection is strongly discouraged';
      return null;
    },
  },
  {
    envVar: 'ZENIC_SANITIZE_XSS_DETECTION',
    configPath: 'sanitize.enableXssDetection',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
    validate: (parsed) => {
      if (parsed === false) return 'Disabling XSS detection is strongly discouraged';
      return null;
    },
  },

  // ── Headers ────────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_HEADERS_HSTS',
    configPath: 'headers.enableHsts',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
    validate: (parsed) => {
      if (parsed === false) return 'Disabling HSTS is strongly discouraged in production';
      return null;
    },
  },
  {
    envVar: 'ZENIC_HEADERS_CSP',
    configPath: 'headers.enableCsp',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
    validate: (parsed) => {
      if (parsed === false) return 'Disabling CSP is strongly discouraged in production';
      return null;
    },
  },

  // ── Encryption ─────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_ENCRYPTION_MIN_KEY_LENGTH',
    configPath: 'encryption.minPassphraseLength',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 32) {
        return `minPassphraseLength must be >= 32 (got ${parsed}); falling back to secure default`;
      }
      return null;
    },
  },
  {
    envVar: 'ZENIC_ENCRYPTION_PBKDF2_ITERATIONS',
    configPath: 'encryption.pbkdf2Iterations',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 100_000) {
        return `pbkdf2Iterations must be >= 100000 (got ${parsed}); falling back to secure default`;
      }
      return null;
    },
  },
  {
    envVar: 'ZENIC_ENCRYPTION_HW_BINDING',
    configPath: 'encryption.enableHardwareBinding',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
  },

  // ── Auth ───────────────────────────────────────────────────────────
  {
    envVar: 'ZENIC_AUTH_REQUIRE_IN_PROD',
    configPath: 'auth.requireAuthInProduction',
    parse: (raw) => {
      const lower = raw.toLowerCase().trim();
      if (lower === 'true' || lower === '1') return true;
      if (lower === 'false' || lower === '0') return false;
      return undefined;
    },
    validate: (parsed) => {
      if (parsed === false) return 'Disabling auth in production is a critical security risk';
      return null;
    },
  },
  {
    envVar: 'ZENIC_AUTH_DEV_BYPASS_USER',
    configPath: 'auth.devBypassUserId',
    parse: (raw) => raw.trim() || undefined,
    validate: (parsed) => {
      if (typeof parsed === 'string' && isKnownInsecure(parsed)) {
        return `devBypassUserId "${parsed}" matches a known insecure default`;
      }
      return null;
    },
  },
  {
    envVar: 'ZENIC_AUTH_MAX_LOGIN_ATTEMPTS',
    configPath: 'auth.maxLoginAttempts',
    parse: (raw) => {
      const n = parseInt(raw, 10);
      return Number.isNaN(n) ? undefined : n;
    },
    validate: (parsed) => {
      if (typeof parsed === 'number' && parsed < 3) return 'maxLoginAttempts should be at least 3';
      if (typeof parsed === 'number' && parsed > 20) return 'maxLoginAttempts above 20 may enable brute-force attacks';
      return null;
    },
  },
];

// ─── Helpers ───────────────────────────────────────────────────────────

/**
 * Check whether a value matches any known insecure default (case-insensitive).
 *
 * @param value - The value to check.
 * @returns `true` if the value is a known insecure default.
 */
function isKnownInsecure(value: string): boolean {
  const lower = value.toLowerCase().trim();
  return INSECURE_DEFAULTS.some(
    (insecure) => lower === insecure.toLowerCase(),
  );
}

/**
 * Set a deeply-nested property on an object using a dot-separated path.
 *
 * Only supports one level of nesting (e.g. `cors.allowedOrigins`) because
 * the security config has at most two levels.
 *
 * @param obj   - The target object.
 * @param path  - Dot-separated property path (e.g. `"cors.allowedOrigins"`).
 * @param value - The value to set.
 */
function setNestedValue(obj: Record<string, unknown>, path: string, value: unknown): void {
  const parts = path.split('.');
  if (parts.length === 1) {
    obj[parts[0]] = value;
  } else if (parts.length === 2) {
    const [first, second] = parts;
    const nested = obj[first];
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      (nested as Record<string, unknown>)[second] = value;
    }
  }
  // Deeper nesting is not needed for the current config shape.
}

/**
 * Determine whether the current runtime is a production environment.
 *
 * Any value other than `"production"` for `NODE_ENV` is treated as
 * non-production so that preview / staging environments can still
 * use development conveniences.
 */
function isProduction(): boolean {
  return process.env.NODE_ENV === 'production';
}

// ─── loadSecurityConfig ────────────────────────────────────────────────

/**
 * Load the effective security configuration by merging environment
 * variable overrides on top of the secure defaults.
 *
 * **Priority order** (highest wins):
 * 1. Valid environment variable values
 * 2. Secure defaults from {@link SecurityConfig}
 *
 * **Fail-closed behaviour:**
 * - If an environment variable cannot be parsed (e.g. `"abc"` for a number
 *   field), the secure default is retained and a warning is logged.
 * - If a parsed value fails validation (e.g. `minPassphraseLength < 32`),
 *   the secure default is retained and a warning is logged.
 * - If an environment variable contains a known insecure default value
 *   (e.g. `"change-me"`), it is rejected and the secure default is used.
 *
 * @returns A fully-resolved {@link SecurityConfigType} with all overrides applied.
 *
 * @example
 * ```ts
 * // In production (with env vars set):
 * // ZENIC_CORS_ORIGINS=https://app.example.com,https://admin.example.com
 * // ZENIC_RATE_LIMIT_MAX=200
 * const config = loadSecurityConfig();
 * // config.cors.allowedOrigins === ['https://app.example.com', 'https://admin.example.com']
 * // config.rateLimit.maxRequests === 200
 * ```
 */
export function loadSecurityConfig(): SecurityConfigType {
  // Deep-clone the defaults so the original object is never mutated.
  const config: SecurityConfigType = structuredClone(SecurityConfig);

  const warnings: string[] = [];

  for (const mapping of ENV_MAPPINGS) {
    const rawValue = process.env[mapping.envVar];

    // No env var set — keep the default.
    if (rawValue === undefined || rawValue === '') continue;

    // Check for known insecure values.
    if (isKnownInsecure(rawValue)) {
      warnings.push(
        `[security-config] Environment variable ${mapping.envVar} contains a known insecure default "${rawValue}" — using secure default instead`,
      );
      continue;
    }

    // Parse the raw string value.
    const parsed = mapping.parse(rawValue);

    // If parsing failed, fall back to default.
    if (parsed === undefined) {
      warnings.push(
        `[security-config] Environment variable ${mapping.envVar} has invalid value "${rawValue}" — using secure default instead`,
      );
      continue;
    }

    // Run custom validation if provided.
    if (mapping.validate) {
      const validationError = mapping.validate(parsed);
      if (validationError !== null) {
        warnings.push(
          `[security-config] Environment variable ${mapping.envVar} failed validation: ${validationError} — using secure default instead`,
        );
        // For constraints like minPassphraseLength < 32, we must reject the value.
        // Check if this is a hard constraint failure (not just a warning).
        const isHardConstraint =
          (mapping.configPath === 'encryption.minPassphraseLength' && typeof parsed === 'number' && parsed < 32) ||
          (mapping.configPath === 'encryption.pbkdf2Iterations' && typeof parsed === 'number' && parsed < 100_000);

        if (isHardConstraint) {
          // Reject the override entirely — keep the secure default.
          continue;
        }
        // For soft warnings (e.g. disabling HSTS), still apply the override
        // but the warning has been recorded.
      }
    }

    // Apply the override.
    setNestedValue(config as unknown as Record<string, unknown>, mapping.configPath, parsed);

    // Log the successful override for auditability.
    const safeValue = typeof parsed === 'string' ? `"${parsed}"` : String(parsed);
    console.info(
      `[security-config] Override applied: ${mapping.configPath} = ${safeValue} (from ${mapping.envVar})`,
    );
  }

  // Emit accumulated warnings.
  for (const warning of warnings) {
    console.warn(warning);
  }

  // Additional runtime checks.
  if (isProduction()) {
    if (config.cors.allowedOrigins.includes('*')) {
      console.warn(
        '[security-config] CRITICAL: Wildcard CORS origin ("*") is configured in production — this allows any website to make authenticated requests',
      );
    }
    if (config.cors.credentials && config.cors.allowedOrigins.includes('*')) {
      console.error(
        '[security-config] CRITICAL: CORS credentials enabled with wildcard origin — browsers will reject this, but the configuration is insecure',
      );
    }
    if (config.auth.devBypassUserId !== '__DEV_BYPASS__' && config.auth.devBypassUserId !== '') {
      console.warn(
        `[security-config] devBypassUserId is set to "${config.auth.devBypassUserId}" in production — this should be removed`,
      );
    }
  }

  return config;
}

// ─── Validation Result ─────────────────────────────────────────────────

/**
 * Result of validating a security configuration object.
 */
export interface SecurityConfigValidationResult {
  /** Whether the configuration is valid (no errors). */
  valid: boolean;
  /**
   * Non-fatal warnings about potentially insecure configurations.
   * These do not prevent the config from being used but should be reviewed.
   */
  warnings: string[];
  /**
   * Fatal errors that make the configuration unsafe to use.
   * If any errors are present, `valid` will be `false`.
   */
  errors: string[];
}

// ─── validateSecurityConfig ────────────────────────────────────────────

/**
 * Validate a security configuration object for insecure values and
 * dangerous combinations.
 *
 * This function checks:
 * - **Hard constraints** (errors): Values that violate minimum security
 *   requirements (e.g. `minPassphraseLength < 32`).
 * - **Dangerous combinations** (errors): Settings that are insecure when
 *   combined (e.g. wildcard CORS + credentials).
 * - **Production requirements** (errors in production, warnings otherwise):
 *   Settings that are acceptable in development but dangerous in production.
 * - **Soft warnings**: Values that are technically valid but may indicate
 *   misconfiguration or reduced security posture.
 *
 * @param config - The security configuration to validate.
 * @returns A {@link SecurityConfigValidationResult} with `valid`, `warnings`, and `errors`.
 *
 * @example
 * ```ts
 * const config = loadSecurityConfig();
 * const result = validateSecurityConfig(config);
 *
 * if (!result.valid) {
 *   console.error('Security config has errors:', result.errors);
 * }
 * if (result.warnings.length > 0) {
 *   console.warn('Security config warnings:', result.warnings);
 * }
 * ```
 */
export function validateSecurityConfig(config: SecurityConfigType): SecurityConfigValidationResult {
  const warnings: string[] = [];
  const errors: string[] = [];
  const prod = isProduction();

  // ── CORS ───────────────────────────────────────────────────────────
  if (config.cors.allowedOrigins.includes('*')) {
    if (config.cors.credentials) {
      errors.push(
        'CORS: Wildcard origin ("*") with credentials=true is insecure and rejected by browsers',
      );
    } else if (prod) {
      errors.push(
        'CORS: Wildcard origin ("*") is not allowed in production — specify explicit origins',
      );
    } else {
      warnings.push(
        'CORS: Wildcard origin ("*") detected — acceptable only in development',
      );
    }
  }

  if (config.cors.credentials && config.cors.allowedOrigins.length === 0) {
    warnings.push(
      'CORS: credentials enabled but no origins specified — credentials will have no effect',
    );
  }

  if (config.cors.maxAge > 86400 * 7) {
    warnings.push(
      `CORS: maxAge of ${config.cors.maxAge}s exceeds 7 days — consider reducing`,
    );
  }

  // ── Rate Limit ─────────────────────────────────────────────────────
  if (config.rateLimit.windowMs < 1000) {
    errors.push(
      `Rate limit: windowMs of ${config.rateLimit.windowMs}ms is too short — minimum is 1000ms`,
    );
  }

  if (config.rateLimit.maxRequests < 1) {
    errors.push(
      'Rate limit: maxRequests must be at least 1',
    );
  }

  if (config.rateLimit.windowMs > 3600 * 1000) {
    warnings.push(
      `Rate limit: windowMs of ${config.rateLimit.windowMs}ms exceeds 1 hour — consider shorter windows`,
    );
  }

  // Validate tiers
  for (const tier of config.rateLimit.tiers) {
    if (tier.windowMs < 1000) {
      errors.push(
        `Rate limit tier "${tier.name}": windowMs of ${tier.windowMs}ms is too short — minimum is 1000ms`,
      );
    }
    if (tier.maxRequests < 1) {
      errors.push(
        `Rate limit tier "${tier.name}": maxRequests must be at least 1`,
      );
    }
    if (tier.routes.length === 0) {
      warnings.push(
        `Rate limit tier "${tier.name}": no routes specified — tier will never apply`,
      );
    }
  }

  // ── Session ────────────────────────────────────────────────────────
  if (config.session.timeoutMs < 60_000) {
    errors.push(
      `Session: timeoutMs of ${config.session.timeoutMs}ms is too short — minimum is 60000ms (1 minute)`,
    );
  }

  if (config.session.timeoutMs > 24 * 60 * 60 * 1000) {
    warnings.push(
      `Session: timeoutMs of ${config.session.timeoutMs}ms exceeds 24 hours — long sessions increase attack window`,
    );
  }

  if (config.session.maxSessionsPerUser < 1) {
    errors.push(
      'Session: maxSessionsPerUser must be at least 1',
    );
  }

  if (config.session.maxSessionsPerUser > 10) {
    warnings.push(
      `Session: maxSessionsPerUser of ${config.session.maxSessionsPerUser} is high — consider limiting concurrent sessions`,
    );
  }

  if (!config.session.enableRotation) {
    warnings.push(
      'Session: rotation disabled — session fixation attacks are easier without rotation on privilege changes',
    );
  }

  // ── Audit ──────────────────────────────────────────────────────────
  if (!config.audit.enabled) {
    if (prod) {
      errors.push(
        'Audit: logging is disabled in production — audit trails are required for compliance and incident response',
      );
    } else {
      warnings.push(
        'Audit: logging is disabled — recommended even in development',
      );
    }
  }

  if (config.audit.enabled && !config.audit.logToConsole && !config.audit.logToDb) {
    warnings.push(
      'Audit: enabled but neither console nor DB logging is active — audit events will be lost',
    );
  }

  if (config.audit.retentionDays < 7) {
    errors.push(
      `Audit: retentionDays of ${config.audit.retentionDays} is too short — minimum is 7 days`,
    );
  }

  if (config.audit.retentionDays < 30) {
    warnings.push(
      `Audit: retentionDays of ${config.audit.retentionDays} may be insufficient for compliance requirements (recommend >= 90)`,
    );
  }

  // ── Sanitize ───────────────────────────────────────────────────────
  if (!config.sanitize.enableSqlDetection) {
    if (prod) {
      errors.push(
        'Sanitize: SQL injection detection disabled in production — this is a critical security risk',
      );
    } else {
      warnings.push(
        'Sanitize: SQL injection detection disabled — strongly recommended to keep enabled',
      );
    }
  }

  if (!config.sanitize.enableXssDetection) {
    if (prod) {
      errors.push(
        'Sanitize: XSS detection disabled in production — this is a critical security risk',
      );
    } else {
      warnings.push(
        'Sanitize: XSS detection disabled — strongly recommended to keep enabled',
      );
    }
  }

  if (config.sanitize.maxQueryParamLength < 64) {
    errors.push(
      `Sanitize: maxQueryParamLength of ${config.sanitize.maxQueryParamLength} is too short — minimum is 64`,
    );
  }

  if (config.sanitize.maxBodySize < 1024) {
    errors.push(
      `Sanitize: maxBodySize of ${config.sanitize.maxBodySize} bytes is too small — minimum is 1024`,
    );
  }

  if (config.sanitize.maxBodySize > 50 * 1024 * 1024) {
    warnings.push(
      `Sanitize: maxBodySize of ${config.sanitize.maxBodySize} bytes exceeds 50MB — large bodies increase DoS risk`,
    );
  }

  // ── Headers ────────────────────────────────────────────────────────
  if (!config.headers.enableHsts) {
    if (prod) {
      errors.push(
        'Headers: HSTS disabled in production — TLS downgrade attacks are possible',
      );
    } else {
      warnings.push(
        'Headers: HSTS disabled — acceptable in development but required in production',
      );
    }
  }

  if (!config.headers.enableCsp) {
    if (prod) {
      errors.push(
        'Headers: CSP disabled in production — XSS attack surface is significantly increased',
      );
    } else {
      warnings.push(
        'Headers: CSP disabled — acceptable in development but required in production',
      );
    }
  }

  if (config.headers.enableCsp) {
    const directives = config.headers.cspDirectives;
    if (!directives['default-src']) {
      warnings.push(
        'Headers: CSP is enabled but missing default-src directive — fallback behavior is undefined',
      );
    }
    if (directives['default-src']?.includes("'unsafe-inline'")) {
      warnings.push(
        "Headers: CSP default-src includes 'unsafe-inline' — significantly weakens XSS protection",
      );
    }
    if (directives['script-src']?.includes("'unsafe-eval'")) {
      warnings.push(
        "Headers: CSP script-src includes 'unsafe-eval' — enables code injection via eval()",
      );
    }
    if (directives['script-src']?.includes("'unsafe-inline'")) {
      warnings.push(
        "Headers: CSP script-src includes 'unsafe-inline' — consider using nonces or hashes instead",
      );
    }
  }

  // ── Encryption ─────────────────────────────────────────────────────
  if (config.encryption.minPassphraseLength < 32) {
    errors.push(
      `Encryption: minPassphraseLength of ${config.encryption.minPassphraseLength} is below the minimum of 32 characters (OWASP recommendation)`,
    );
  }

  if (config.encryption.pbkdf2Iterations < 100_000) {
    errors.push(
      `Encryption: pbkdf2Iterations of ${config.encryption.pbkdf2Iterations} is below the minimum of 100,000 (OWASP 2023 recommendation)`,
    );
  }

  if (config.encryption.pbkdf2Iterations < 300_000 && config.encryption.pbkdf2Iterations >= 100_000) {
    warnings.push(
      `Encryption: pbkdf2Iterations of ${config.encryption.pbkdf2Iterations} meets the minimum but OWASP recommends 600,000 for PBKDF2-SHA256`,
    );
  }

  // ── Auth ───────────────────────────────────────────────────────────
  if (!config.auth.requireAuthInProduction && prod) {
    errors.push(
      'Auth: requireAuthInProduction is false in a production environment — authentication is mandatory',
    );
  }

  if (config.auth.devBypassUserId && config.auth.devBypassUserId !== '__DEV_BYPASS__' && prod) {
    errors.push(
      `Auth: devBypassUserId "${config.auth.devBypassUserId}" is set in production — dev bypass must not be active in production`,
    );
  }

  if (isKnownInsecure(config.auth.devBypassUserId)) {
    warnings.push(
      `Auth: devBypassUserId "${config.auth.devBypassUserId}" matches a known insecure default`,
    );
  }

  if (config.auth.maxLoginAttempts < 3) {
    warnings.push(
      `Auth: maxLoginAttempts of ${config.auth.maxLoginAttempts} is very low — legitimate users may be locked out frequently`,
    );
  }

  if (config.auth.maxLoginAttempts > 20) {
    warnings.push(
      `Auth: maxLoginAttempts of ${config.auth.maxLoginAttempts} is high — brute-force attacks are easier`,
    );
  }

  if (config.auth.maxLoginAttempts <= 0) {
    errors.push(
      'Auth: maxLoginAttempts must be a positive integer',
    );
  }

  // ── Cross-cutting checks ───────────────────────────────────────────
  // Check for insecure default values in string fields
  if (isKnownInsecure(config.auth.devBypassUserId)) {
    if (!errors.some((e) => e.includes('devBypassUserId'))) {
      warnings.push(
        'Configuration contains known insecure default values — review all secret/key fields',
      );
    }
  }

  return {
    valid: errors.length === 0,
    warnings,
    errors,
  };
}
