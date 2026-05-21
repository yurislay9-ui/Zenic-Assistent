/**
 * @module sanitize
 * @description Comprehensive query parameter and input sanitizer for the Zenic-Agents gateway.
 *
 * Provides strict but fair sanitization and validation for all inbound user-controlled
 * inputs: URL search parameters, path parameters, free-form strings, and more.
 *
 * Security checks include:
 * - SQL injection detection
 * - XSS (cross-site scripting) detection
 * - Path traversal detection
 * - Type-safe path parameter validation (UUID, alphanumeric, CUID, numeric)
 * - Configurable string sanitization with length limits and HTML policy
 *
 * All rejected attempts are logged via `console.warn` with a `[sanitize]` prefix
 * so they can be surfaced in observability pipelines.
 *
 * @example
 * ```ts
 * import { sanitizeSearchParams, validatePathParam, withSanitizedParams } from '@/lib/security/sanitize';
 *
 * // Sanitize query params
 * const clean = sanitizeSearchParams(new URLSearchParams(request.url));
 *
 * // Validate a UUID path param
 * const tenantId = validatePathParam('tenantId', params.tenantId, 'uuid');
 *
 * // Wrap a route handler
 * export const GET = withSanitizedParams(async (req, ctx) => { ... });
 * ```
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Supported format types for path parameter validation. */
export type PathParamType = 'uuid' | 'alphanumeric' | 'cuid' | 'numeric';

/** Options for {@link sanitizeString}. */
export interface SanitizeStringOptions {
  /** Maximum allowed length for the input string. Defaults to `1024`. */
  maxLength?: number;
  /**
   * Whether to allow HTML content in the string.
   * When `false` (default), any HTML tags or entities are stripped / rejected.
   */
  allowHtml?: boolean;
}

/** Result returned by detection helpers when a threat is found. */
export interface ThreatDetectionResult {
  /** Whether a threat was detected. */
  detected: boolean;
  /** Human-readable description of the threat (empty string when clean). */
  reason: string;
}

/** Extended request type used by {@link withSanitizedParams}. */
export interface SanitizedRequest extends Request {
  /** Sanitized query parameters. */
  sanitizedQuery: Record<string, string>;
  /** Sanitized path parameters (populated from route context when available). */
  sanitizedParams: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Regex patterns
// ---------------------------------------------------------------------------

/**
 * UUID v1-v8 regex.
 * Matches `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` with hex digits.
 */
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * CUID / CUID2 regex.
 * CUID1: starts with `c`, followed by 24+ lowercase alphanumeric chars.
 * CUID2: 24+ lowercase alphanumeric chars (may not start with `c`).
 * We accept both forms loosely.
 */
const CUID_REGEX = /^[a-z0-9]{8,32}$/i;

/** Alphanumeric (plus hyphen and underscore) — typical for slugs. */
const ALPHANUMERIC_REGEX = /^[a-zA-Z0-9_-]+$/;

/** Pure numeric string. */
const NUMERIC_REGEX = /^[0-9]+$/;

/**
 * SQL injection keywords used for multi-signal detection.
 * Looks for SQL keywords combined with suspicious characters/patterns.
 */
const SQL_KEYWORDS = [
  'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE',
  'EXEC', 'EXECUTE', 'UNION', 'CREATE', 'GRANT', 'REVOKE', 'MERGE',
  'HAVING', 'GROUP BY', 'ORDER BY',
] as const;

const SQL_DANGEROUS_PATTERNS = [
  /;\s*(SELECT|DROP|ALTER|DELETE|INSERT|UPDATE|CREATE|EXEC)\b/i,
  /'(\s)*(OR|AND)\s+/i,
  /\b(OR|AND)\s+\d+\s*=\s*\d+/i,
  /\b(OR|AND)\s+'[^']*'\s*=\s*'[^']*'/i,
  /UNION\s+(ALL\s+)?SELECT\b/i,
  /--\s*$/m,
  /\/\*[\s\S]*?\*\//,
  /\bxp_cmdshell\b/i,
  /\b0x[0-9a-f]{8,}\b/i,
  /CHAR\s*\(\s*\d+/i,
  /CONCAT\s*\(/i,
  /BENCHMARK\s*\(/i,
  /SLEEP\s*\(/i,
  /WAITFOR\s+DELAY\b/i,
] as const;

/**
 * XSS detection patterns.
 * Matches script tags, event handler attributes, javascript: URIs,
 * and dangerous SVG/HTML constructs.
 */
const XSS_PATTERNS = [
  /<script\b[^>]*>[\s\S]*?<\/script>/gi,
  /<script\b[^>]*\/?>/gi,
  /\bon\w+\s*=\s*["']?/gi,                       // on<event>=
  /\bjavascript\s*:/gi,
  /\bvbscript\s*:/gi,
  /<\s*iframe\b/gi,
  /<\s*object\b/gi,
  /<\s*embed\b/gi,
  /<\s*form\b/gi,
  /<\s*link\b[^>]*\brel\s*=\s*["']?import/gi,
  /<\s*svg\b[^>]*\bon\w+/gi,
  /<\s*math\b[^>]*\bon\w+/gi,
  /<\s*img\b[^>]*\bon\w+/gi,
  /<\s*input\b[^>]*\bon\w+/gi,
  /<\s*body\b[^>]*\bon\w+/gi,
  /expression\s*\(/gi,
  /url\s*\(\s*["']?\s*javascript:/gi,
  /-moz-binding\s*:/gi,
  /data\s*:\s*text\/html/gi,
] as const;

/**
 * Path traversal patterns.
 * Catches `../`, `..\\`, URL-encoded variants, and absolute Unix/Windows paths.
 */
const PATH_TRAVERSAL_PATTERNS = [
  /\.\./,                     // ../ or ..\
  /\.\.\//,
  /\.\.\\/,
  /%2e%2e[\\/]/i,
  /%252e/i,                   // double-encoded
  /\.\.%2f/i,
  /\.\.%5c/i,
  /^\//,                      // absolute Unix path
  /^[A-Za-z]:\\/,             // absolute Windows path
] as const;

/** Characters that are stripped from query parameter values by default. */
const STRIP_CHARS_REGEX = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;

// ---------------------------------------------------------------------------
// Detection helpers
// ---------------------------------------------------------------------------

/**
 * Detect SQL injection patterns in a string.
 *
 * Uses a multi-signal approach: checks for SQL keywords combined with
 * suspicious patterns like tautologies, union-select, semicolons with
 * DML keywords, encoded hex, and timing-attack vectors.
 *
 * @param input - The string to check.
 * @returns A {@link ThreatDetectionResult} indicating whether a threat was found.
 *
 * @example
 * ```ts
 * detectSqlInjection("1 OR 1=1");       // { detected: true, reason: "..." }
 * detectSqlInjection("hello world");     // { detected: false, reason: "" }
 * ```
 */
export function detectSqlInjection(input: string): ThreatDetectionResult {
  // Short, purely numeric/alphanumeric inputs are safe
  if (input.length < 5 && /^[a-zA-Z0-9_-]+$/.test(input)) {
    return { detected: false, reason: '' };
  }

  // Check dangerous pattern matches first
  for (const pattern of SQL_DANGEROUS_PATTERNS) {
    if (pattern.test(input)) {
      console.warn('[sanitize] SQL injection detected:', { input: truncateForLog(input), pattern: pattern.source });
      return { detected: true, reason: `SQL injection pattern matched: ${pattern.source}` };
    }
  }

  // Multi-signal: count how many SQL keywords appear; if 2+ in a longer string, suspicious
  const upper = input.toUpperCase();
  let keywordHits = 0;
  for (const kw of SQL_KEYWORDS) {
    // Use word-boundary-aware check to avoid false positives inside other words
    const kwRegex = new RegExp(`\\b${kw}\\b`, 'i');
    if (kwRegex.test(input)) {
      keywordHits++;
    }
  }
  if (keywordHits >= 2 && input.length > 10) {
    console.warn('[sanitize] SQL injection suspected (multi-keyword):', { input: truncateForLog(input), keywordHits });
    return { detected: true, reason: `Multiple SQL keywords detected (${keywordHits}) in input` };
  }

  return { detected: false, reason: '' };
}

/**
 * Detect XSS (cross-site scripting) patterns in a string.
 *
 * Checks for script tags, inline event handlers (`onclick`, `onerror`, etc.),
 * `javascript:` URIs, dangerous HTML elements (iframe, object, embed),
 * and CSS-based attacks (`expression()`, `-moz-binding`).
 *
 * @param input - The string to check.
 * @returns A {@link ThreatDetectionResult} indicating whether a threat was found.
 *
 * @example
 * ```ts
 * detectXss('<script>alert(1)</script>');  // { detected: true, reason: "..." }
 * detectXss('plain text');                  // { detected: false, reason: "" }
 * ```
 */
export function detectXss(input: string): ThreatDetectionResult {
  for (const pattern of XSS_PATTERNS) {
    if (pattern.test(input)) {
      console.warn('[sanitize] XSS detected:', { input: truncateForLog(input), pattern: pattern.source });
      return { detected: true, reason: `XSS pattern matched: ${pattern.source}` };
    }
  }
  return { detected: false, reason: '' };
}

/**
 * Detect path traversal attempts in a string.
 *
 * Catches `../`, `..\\`, URL-encoded and double-encoded variants,
 * as well as absolute Unix (`/etc/passwd`) and Windows (`C:\`) paths.
 *
 * @param input - The string to check.
 * @returns A {@link ThreatDetectionResult} indicating whether a threat was found.
 *
 * @example
 * ```ts
 * detectPathTraversal('../../etc/passwd');  // { detected: true, reason: "..." }
 * detectPathTraversal('reports/q1');         // { detected: false, reason: "" }
 * ```
 */
export function detectPathTraversal(input: string): ThreatDetectionResult {
  for (const pattern of PATH_TRAVERSAL_PATTERNS) {
    if (pattern.test(input)) {
      console.warn('[sanitize] Path traversal detected:', { input: truncateForLog(input), pattern: pattern.source });
      return { detected: true, reason: `Path traversal pattern matched: ${pattern.source}` };
    }
  }
  return { detected: false, reason: '' };
}

// ---------------------------------------------------------------------------
// Core sanitizers
// ---------------------------------------------------------------------------

/**
 * Sanitize a free-form string input.
 *
 * Performs the following steps in order:
 * 1. Trim leading/trailing whitespace.
 * 2. Strip null bytes and control characters (except `\t`, `\n`, `\r`).
 * 3. Check length against `opts.maxLength` (default 1024).
 * 4. Run SQL injection detection.
 * 5. Run XSS detection (unless `opts.allowHtml` is `true`).
 * 6. Run path traversal detection.
 * 7. If `allowHtml` is `false`, strip remaining HTML tags.
 *
 * **Throws** a `SanitizationError` when a security threat is detected.
 * **Truncates** (with a warning) when the input exceeds `maxLength`.
 *
 * @param input - The raw string to sanitize.
 * @param opts  - Optional configuration. See {@link SanitizeStringOptions}.
 * @returns The sanitized string.
 * @throws {SanitizationError} When SQL injection, XSS, or path traversal is detected.
 *
 * @example
 * ```ts
 * sanitizeString('hello world');                              // 'hello world'
 * sanitizeString('<b>bold</b>');                              // 'bold' (HTML stripped)
 * sanitizeString('<b>bold</b>', { allowHtml: true });         // '<b>bold</b>'
 * sanitizeString('a'.repeat(2000), { maxLength: 500 });       // truncated to 500
 * sanitizeString('1 OR 1=1');                                 // throws SanitizationError
 * ```
 */
export function sanitizeString(input: string, opts?: SanitizeStringOptions): string {
  const maxLength = opts?.maxLength ?? 1024;
  const allowHtml = opts?.allowHtml ?? false;

  if (typeof input !== 'string') {
    console.warn('[sanitize] Non-string input received, converting to string');
    input = String(input);
  }

  // 1. Trim
  let sanitized = input.trim();

  // 2. Strip control characters (keep tab, LF, CR)
  sanitized = sanitized.replace(STRIP_CHARS_REGEX, '');

  // 3. Length check
  if (sanitized.length > maxLength) {
    console.warn('[sanitize] Input exceeded maxLength, truncating:', {
      originalLength: sanitized.length,
      maxLength,
      preview: truncateForLog(sanitized),
    });
    sanitized = sanitized.slice(0, maxLength);
  }

  // 4. SQL injection detection
  const sqlResult = detectSqlInjection(sanitized);
  if (sqlResult.detected) {
    throw new SanitizationError(`SQL injection detected: ${sqlResult.reason}`);
  }

  // 5. XSS detection (unless HTML is explicitly allowed)
  if (!allowHtml) {
    const xssResult = detectXss(sanitized);
    if (xssResult.detected) {
      throw new SanitizationError(`XSS detected: ${xssResult.reason}`);
    }
  }

  // 6. Path traversal detection
  const traversalResult = detectPathTraversal(sanitized);
  if (traversalResult.detected) {
    throw new SanitizationError(`Path traversal detected: ${traversalResult.reason}`);
  }

  // 7. Strip HTML tags if not allowed
  if (!allowHtml) {
    sanitized = stripHtmlTags(sanitized);
  }

  return sanitized;
}

/**
 * Validate a path parameter against an expected format.
 *
 * Supported types:
 * - `'uuid'`        — UUID v1–v8 (8-4-4-4-12 hex digits).
 * - `'alphanumeric'` — Letters, digits, hyphens, underscores.
 * - `'cuid'`        — CUID/CUID2 identifiers (8–32 lowercase alphanumeric).
 * - `'numeric'`     — Pure digit string.
 *
 * Also runs full security checks (SQL injection, XSS, path traversal)
 * regardless of type, for defense-in-depth.
 *
 * **Throws** a `SanitizationError` when validation fails.
 *
 * @param name  - The parameter name (for error messages and logging).
 * @param value - The raw value to validate.
 * @param type  - The expected format type.
 * @returns The validated value (unchanged if valid).
 * @throws {SanitizationError} When the value does not match the expected format or contains threats.
 *
 * @example
 * ```ts
 * validatePathParam('requestId', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'uuid');
 * validatePathParam('page', '3', 'numeric');
 * validatePathParam('slug', 'my-resource_v2', 'alphanumeric');
 * ```
 */
export function validatePathParam(name: string, value: string, type: PathParamType): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new SanitizationError(`Path parameter "${name}" is empty or not a string`);
  }

  // Defense-in-depth: run all security checks first
  const sqlResult = detectSqlInjection(value);
  if (sqlResult.detected) {
    throw new SanitizationError(`Path parameter "${name}" failed SQL injection check: ${sqlResult.reason}`);
  }

  const xssResult = detectXss(value);
  if (xssResult.detected) {
    throw new SanitizationError(`Path parameter "${name}" failed XSS check: ${xssResult.reason}`);
  }

  const traversalResult = detectPathTraversal(value);
  if (traversalResult.detected) {
    throw new SanitizationError(`Path parameter "${name}" failed path traversal check: ${traversalResult.reason}`);
  }

  // Type-specific validation
  switch (type) {
    case 'uuid': {
      if (!UUID_REGEX.test(value)) {
        throw new SanitizationError(
          `Path parameter "${name}" is not a valid UUID: "${truncateForLog(value)}"`,
        );
      }
      break;
    }
    case 'alphanumeric': {
      if (!ALPHANUMERIC_REGEX.test(value)) {
        throw new SanitizationError(
          `Path parameter "${name}" contains non-alphanumeric characters: "${truncateForLog(value)}"`,
        );
      }
      break;
    }
    case 'cuid': {
      if (!CUID_REGEX.test(value)) {
        throw new SanitizationError(
          `Path parameter "${name}" is not a valid CUID: "${truncateForLog(value)}"`,
        );
      }
      break;
    }
    case 'numeric': {
      if (!NUMERIC_REGEX.test(value)) {
        throw new SanitizationError(
          `Path parameter "${name}" is not a valid numeric string: "${truncateForLog(value)}"`,
        );
      }
      break;
    }
    default: {
      const _exhaustive: never = type;
      throw new SanitizationError(`Unknown path parameter type: ${String(type)}`);
    }
  }

  return value;
}

/**
 * Sanitize all entries in a `URLSearchParams` object.
 *
 * For each key-value pair:
 * 1. Strips control characters from the value.
 * 2. Runs full security checks (SQL injection, XSS, path traversal).
 * 3. Truncates values longer than 2048 characters.
 * 4. Strips HTML tags from values.
 * 5. Skips entries that fail security checks (logs a warning) rather than throwing,
 *    so that a single malicious parameter does not block the entire request.
 *    Callers who need strict fail-fast behaviour should use {@link sanitizeString} directly.
 *
 * @param searchParams - The `URLSearchParams` from an incoming request.
 * @returns A clean `Record<string, string>` with only safe values.
 *
 * @example
 * ```ts
 * const url = new URL(request.url);
 * const clean = sanitizeSearchParams(url.searchParams);
 * // clean = { page: '2', sort: 'name' }
 * ```
 */
export function sanitizeSearchParams(searchParams: URLSearchParams): Record<string, string> {
  const clean: Record<string, string> = {};
  const MAX_QUERY_VALUE_LENGTH = 2048;

  for (const [key, value] of searchParams.entries()) {
    // Sanitize the key itself (strip control chars)
    const cleanKey = key.replace(STRIP_CHARS_REGEX, '').trim();

    if (cleanKey.length === 0) {
      console.warn('[sanitize] Skipping search param with empty key:', { originalKey: truncateForLog(key) });
      continue;
    }

    try {
      // Strip control characters
      let cleanValue = value.replace(STRIP_CHARS_REGEX, '').trim();

      // Truncate oversized values
      if (cleanValue.length > MAX_QUERY_VALUE_LENGTH) {
        console.warn('[sanitize] Query param value truncated:', {
          key: cleanKey,
          originalLength: cleanValue.length,
          max: MAX_QUERY_VALUE_LENGTH,
        });
        cleanValue = cleanValue.slice(0, MAX_QUERY_VALUE_LENGTH);
      }

      // Security checks
      const sqlResult = detectSqlInjection(cleanValue);
      if (sqlResult.detected) {
        console.warn('[sanitize] Skipping query param with SQL injection:', { key: cleanKey });
        continue;
      }

      const xssResult = detectXss(cleanValue);
      if (xssResult.detected) {
        console.warn('[sanitize] Skipping query param with XSS:', { key: cleanKey });
        continue;
      }

      const traversalResult = detectPathTraversal(cleanValue);
      if (traversalResult.detected) {
        console.warn('[sanitize] Skipping query param with path traversal:', { key: cleanKey });
        continue;
      }

      // Strip HTML tags
      cleanValue = stripHtmlTags(cleanValue);

      clean[cleanKey] = cleanValue;
    } catch (err) {
      console.warn('[sanitize] Skipping query param due to error:', {
        key: cleanKey,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  return clean;
}

// ---------------------------------------------------------------------------
// Middleware helper
// ---------------------------------------------------------------------------

/**
 * Type describing the context object passed to route handlers.
 * Compatible with Next.js App Router, Express, and custom frameworks.
 */
export interface RouteContext {
  /** Path parameters extracted by the router (e.g. `{ requestId: '...' }`). */
  params?: Record<string, string | undefined>;
  /** Additional context (framework-specific). */
  [key: string]: unknown;
}

/**
 * Type describing a route handler compatible with {@link withSanitizedParams}.
 */
export type RouteHandler = (
  req: SanitizedRequest,
  ctx: RouteContext,
) => Promise<Response> | Response;

/**
 * Route parameter validation specification.
 * Each entry maps a path parameter name to its expected type.
 */
export type ParamValidationSpec = Record<string, PathParamType>;

/**
 * Default path parameter validation spec for common Zenic-Agents identifiers.
 * Override or extend this by passing a custom spec to {@link withSanitizedParams}.
 */
export const DEFAULT_PARAM_SPEC: ParamValidationSpec = {
  requestId: 'uuid',
  tenantId: 'uuid',
  policyId: 'uuid',
  approvalId: 'uuid',
  namespaceId: 'alphanumeric',
  version: 'numeric',
};

/**
 * Wrap a route handler with automatic query and path parameter sanitization.
 *
 * When the handler is invoked:
 * 1. Query parameters are sanitized via {@link sanitizeSearchParams} and attached as
 *    `req.sanitizedQuery`.
 * 2. Path parameters are validated via {@link validatePathParam} using the provided
 *    (or default) spec and attached as `req.sanitizedParams`.
 * 3. If any path parameter fails validation, a `400 Bad Request` response is returned
 *    immediately with a JSON error body.
 *
 * @param handler - The route handler to wrap.
 * @param paramSpec - Optional per-parameter validation spec. Defaults to {@link DEFAULT_PARAM_SPEC}.
 * @returns A wrapped handler that performs sanitization before delegating.
 *
 * @example
 * ```ts
 * export const GET = withSanitizedParams(async (req, ctx) => {
 *   const { tenantId } = req.sanitizedParams;   // validated UUID
 *   const { page, limit } = req.sanitizedQuery;  // clean strings
 *   // ...
 *   return Response.json({ data: [] });
 * });
 *
 * // With custom param spec
 * export const GET = withSanitizedParams(
 *   async (req, ctx) => { ... },
 *   { orgId: 'alphanumeric', page: 'numeric' },
 * );
 * ```
 */
export function withSanitizedParams(
  handler: RouteHandler,
  paramSpec: ParamValidationSpec = DEFAULT_PARAM_SPEC,
): RouteHandler {
  return async (req: SanitizedRequest, ctx: RouteContext): Promise<Response> => {
    // --- Sanitize query parameters ---
    let url: URL;
    try {
      url = new URL(req.url);
    } catch {
      console.warn('[sanitize] Could not parse request URL');
      return Response.json(
        { error: 'Invalid request URL' },
        { status: 400 },
      );
    }

    req.sanitizedQuery = sanitizeSearchParams(url.searchParams);

    // --- Validate path parameters ---
    const rawParams = ctx.params ?? {};
    const sanitizedParams: Record<string, string> = {};

    for (const [name, type] of Object.entries(paramSpec)) {
      const rawValue = rawParams[name];
      if (rawValue === undefined || rawValue === null) {
        // Parameter not present in this route — skip silently
        continue;
      }

      try {
        sanitizedParams[name] = validatePathParam(name, String(rawValue), type);
      } catch (err) {
        const message = err instanceof SanitizationError
          ? err.message
          : `Path parameter "${name}" failed validation`;
        console.warn('[sanitize] Path param validation failed:', { name, message });
        return Response.json(
          { error: 'Bad Request', detail: message },
          { status: 400 },
        );
      }
    }

    // Copy over any path params not in the spec (still sanitize them as strings)
    for (const [name, rawValue] of Object.entries(rawParams)) {
      if (!(name in paramSpec) && rawValue != null) {
        try {
          sanitizedParams[name] = sanitizeString(String(rawValue), { maxLength: 256 });
        } catch (err) {
          const message = err instanceof SanitizationError
            ? err.message
            : `Path parameter "${name}" failed sanitization`;
          console.warn('[sanitize] Unschemed path param sanitization failed:', { name, message });
          return Response.json(
            { error: 'Bad Request', detail: message },
            { status: 400 },
          );
        }
      }
    }

    req.sanitizedParams = sanitizedParams;

    // --- Delegate to the real handler ---
    return handler(req, ctx);
  };
}

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

/**
 * Error thrown when input sanitization or validation fails.
 *
 * Uses a distinct class so callers can differentiate sanitization errors
 * from generic runtime errors.
 */
export class SanitizationError extends Error {
  /** Machine-readable code identifying the failure category. */
  public readonly code: 'SANITIZATION_ERROR';

  constructor(message: string) {
    super(message);
    this.name = 'SanitizationError';
    this.code = 'SANITIZATION_ERROR';

    // Restore prototype chain (required for classes extending built-ins in TS)
    Object.setPrototypeOf(this, SanitizationError.prototype);
  }
}

// ---------------------------------------------------------------------------
// Internal utilities
// ---------------------------------------------------------------------------

/**
 * Strip HTML tags from a string.
 *
 * Removes anything that looks like an HTML tag (`<...>`) and decodes
 * the most common HTML entities to prevent entity-based bypass.
 *
 * This is a **lossy** operation intended for non-HTML contexts.
 * When `allowHtml: true` is passed to {@link sanitizeString}, this step is skipped.
 *
 * @param input - The string to strip HTML from.
 * @returns The string with HTML tags removed and common entities decoded.
 */
function stripHtmlTags(input: string): string {
  // Remove HTML tags
  let result = input.replace(/<[^>]*>/g, '');

  // Decode common HTML entities to prevent entity-based bypass
  const ENTITY_MAP: Record<string, string> = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'",
    '&#x27;': "'",
    '&#x2F;': '/',
    '&#x3C;': '<',
    '&#x3E;': '>',
  };

  for (const [entity, char] of Object.entries(ENTITY_MAP)) {
    result = result.replaceAll(entity, char);
  }

  // Decode numeric HTML entities (decimal)
  result = result.replace(/&#(\d{1,7});/g, (_, code) => {
    const num = Number(code);
    if (num > 0 && num <= 0x10ffff) {
      return String.fromCodePoint(num);
    }
    return '';
  });

  // Decode numeric HTML entities (hex)
  result = result.replace(/&#x([0-9a-fA-F]{1,6});/g, (_, hex) => {
    const num = parseInt(hex, 16);
    if (num > 0 && num <= 0x10ffff) {
      return String.fromCodePoint(num);
    }
    return '';
  });

  return result;
}

/**
 * Truncate a string for safe inclusion in log output.
 *
 * Prevents accidentally logging very large inputs (e.g. base64 payloads).
 *
 * @param input - The string to truncate.
 * @param maxLen - Maximum length before truncation. Defaults to 120.
 * @returns The possibly-truncated string with a `...` suffix if truncated.
 */
function truncateForLog(input: string, maxLen = 120): string {
  if (input.length <= maxLen) return input;
  return `${input.slice(0, maxLen)}...`;
}
