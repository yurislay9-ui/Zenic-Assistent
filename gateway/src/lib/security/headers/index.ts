// ─── Zenic-Agents Gateway — Security HTTP Headers Module ─────────────
// Provides comprehensive security header management for all gateway
// responses. Implements G1+G2 security posture with production-ready
// defaults for CSP, HSTS, clickjacking protection, MIME sniffing
// prevention, referrer leakage controls, and permissions policy.

import { NextResponse } from 'next/server';

// ─── Type Definitions ───────────────────────────────────────────────

/**
 * Options for customising the security headers applied to a response.
 *
 * All fields are optional — when omitted the production-ready defaults
 * from {@link getDefaultSecurityHeaders} are used.
 *
 * @example
 * ```ts
 * applySecurityHeaders(response, {
 *   cspOverrides: { 'script-src': ["'self'", 'cdn.example.com'] },
 *   disableHsts: true,
 *   customFrameOptions: 'SAMEORIGIN',
 *   additionalHeaders: { 'X-Custom-Security': 'enabled' },
 *   skipHeaders: ['X-XSS-Protection'],
 * });
 * ```
 */
export interface SecurityHeaderOptions {
  /**
   * Override specific CSP directives. Each key is a CSP directive name
   * (e.g. `'script-src'`, `'img-src'`) and the value is the complete
   * list of sources for that directive, replacing the default entirely.
   *
   * Directives not listed here retain their default values.
   */
  cspOverrides?: Record<string, string[]>;

  /**
   * When `true`, the `Strict-Transport-Security` header is omitted
   * regardless of the environment. Useful for health-check endpoints
   * or non-HTTPS routes.
   *
   * In development mode HSTS is always disabled.
   * @default false
   */
  disableHsts?: boolean;

  /**
   * Override the default `X-Frame-Options` value.
   * Common values: `'DENY'`, `'SAMEORIGIN'`.
   * When omitted, defaults to `'DENY'`.
   */
  customFrameOptions?: string;

  /**
   * Additional custom headers to merge into the response.
   * These are applied after the standard security headers, so they
   * can override defaults if needed.
   */
  additionalHeaders?: Record<string, string>;

  /**
   * List of header names to skip entirely.
   * Use this to selectively disable specific security headers for
   * routes that require different behaviour (e.g. iframe embedding).
   *
   * Names are matched case-insensitively against the standard header set.
   */
  skipHeaders?: string[];
}

// ─── Security Header Name Constants ─────────────────────────────────

/**
 * Canonical names for all security-related HTTP headers used by the
 * Zenic-Agents gateway.
 *
 * Using constants avoids typos and provides a single source of truth
 * for header names across the codebase.
 *
 * @example
 * ```ts
 * response.headers.set(SecurityHeaders.ContentTypeOptions, 'nosniff');
 * ```
 */
export const SecurityHeaders = {
  /** Content-Security-Policy — controls which resources the browser may load. */
  ContentSecurityPolicy: 'Content-Security-Policy',

  /** X-Frame-Options — prevents clickjacking by controlling iframe embedding. */
  FrameOptions: 'X-Frame-Options',

  /** X-Content-Type-Options — prevents MIME-type sniffing. */
  ContentTypeOptions: 'X-Content-Type-Options',

  /** X-XSS-Protection — legacy XSS filter control (disabled; CSP is preferred). */
  XssProtection: 'X-XSS-Protection',

  /** Referrer-Policy — controls how much referrer information is shared. */
  ReferrerPolicy: 'Referrer-Policy',

  /** Permissions-Policy — controls which browser features and APIs may be used. */
  PermissionsPolicy: 'Permissions-Policy',

  /** Strict-Transport-Security — enforces HTTPS connections (HSTS). */
  StrictTransportSecurity: 'Strict-Transport-Security',

  /** X-Request-ID — unique identifier for request tracing. */
  RequestId: 'X-Request-ID',

  /** Cache-Control — caching directives for sensitive routes. */
  CacheControl: 'Cache-Control',
} as const;

// ─── Default CSP Directives ─────────────────────────────────────────

/**
 * Production-ready default Content Security Policy directives.
 *
 * Policy:
 * - `default-src 'self'`        — Only allow resources from the same origin
 * - `script-src 'self'`         — Only allow scripts from the same origin
 * - `style-src 'self' 'unsafe-inline'` — Allow same-origin styles and inline
 *                                         styles (required for many CSS-in-JS
 *                                         frameworks)
 * - `img-src 'self' data:`      — Allow same-origin images and data URIs
 * - `connect-src 'self'`        — Only allow XHR/Fetch to the same origin
 * - `frame-ancestors 'none'`    — Prevent the page from being embedded in
 *                                   iframes (stronger than X-Frame-Options)
 * - `base-uri 'self'`           — Restrict `<base>` tag to same origin
 * - `form-action 'self'`        — Only allow form submissions to same origin
 */
const DEFAULT_CSP_DIRECTIVES: Record<string, string[]> = {
  'default-src': ["'self'"],
  'script-src': ["'self'"],
  'style-src': ["'self'", "'unsafe-inline'"],
  'img-src': ["'self'", 'data:'],
  'connect-src': ["'self'"],
  'frame-ancestors': ["'none'"],
  'base-uri': ["'self'"],
  'form-action': ["'self'"],
};

/**
 * Default permissions policy that disables all sensitive browser APIs.
 *
 * All features are set to `()` (empty allowlist = disabled), preventing
 * web pages from accessing camera, microphone, geolocation, payment,
 * USB, magnetometer, gyroscope, and accelerometer APIs.
 */
const DEFAULT_PERMISSIONS_POLICY =
  'camera=(), microphone=(), geolocation=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()';

// ─── Environment Detection ──────────────────────────────────────────

/**
 * Determine if the current runtime is a production environment.
 *
 * Checks `process.env.NODE_ENV` — any value other than `'production'`
 * is treated as non-production (development, test, staging, etc.).
 *
 * @returns `true` when running in production, `false` otherwise.
 */
function isProduction(): boolean {
  return process.env.NODE_ENV === 'production';
}

// ─── Core Functions ─────────────────────────────────────────────────

/**
 * Returns the HSTS (HTTP Strict Transport Security) header value for
 * the current environment.
 *
 * **Production only** — in development or test environments this
 * returns `null` because HSTS should never be applied over plain HTTP
 * or in environments where certificates may be self-signed.
 *
 * Production value: `max-age=63072000; includeSubDomains; preload`
 * - `max-age=63072000`  — ~2 years, per Mozilla recommendations
 * - `includeSubDomains`  — HSTS applies to all subdomains
 * - `preload`            — Eligible for browser HSTS preload lists
 *
 * @returns The HSTS header value string, or `null` in non-production.
 *
 * @example
 * ```ts
 * const hsts = getHstsHeader();
 * if (hsts) {
 *   response.headers.set(SecurityHeaders.StrictTransportSecurity, hsts);
 * }
 * ```
 */
export function getHstsHeader(): string | null {
  if (!isProduction()) {
    return null;
  }
  return 'max-age=63072000; includeSubDomains; preload';
}

/**
 * Build a Content-Security-Policy header value from a directives map.
 *
 * Each key is a CSP directive name (e.g. `'script-src'`) and the value
 * is an array of source expressions (e.g. `["'self'", 'cdn.example.com']`).
 * The resulting header value joins each directive with its sources
 * using a semicolon separator.
 *
 * @param directives - CSP directives to include. When omitted, uses
 *                     {@link DEFAULT_CSP_DIRECTIVES}.
 * @returns The formatted CSP header value string.
 *
 * @example
 * ```ts
 * // Using defaults
 * createCspHeader();
 * // → "default-src 'self'; script-src 'self'; ..."
 *
 * // With custom directives
 * createCspHeader({
 *   'default-src': ["'self'"],
 *   'script-src': ["'self'", 'analytics.example.com'],
 *   'img-src': ["'self'", 'data:', 'cdn.example.com'],
 * });
 * // → "default-src 'self'; script-src 'self' analytics.example.com; img-src 'self' data: cdn.example.com"
 * ```
 */
export function createCspHeader(
  directives?: Record<string, string[]>
): string {
  const merged = { ...DEFAULT_CSP_DIRECTIVES, ...directives };

  return Object.entries(merged)
    .map(([directive, sources]) => `${directive} ${sources.join(' ')}`)
    .join('; ');
}

/**
 * Returns the full set of production-ready security headers with their
 * default values.
 *
 * This function returns a plain `Record<string, string>` suitable for
 * spreading onto response headers or passing to header-setting APIs.
 *
 * **Environment-aware behaviour:**
 * - In **production**: includes `Strict-Transport-Security` with a
 *   2-year max-age, `includeSubDomains`, and `preload`.
 * - In **development/test**: omits HSTS entirely.
 *
 * The returned headers represent the **G1+G2 security posture** for the
 * Zenic-Agents gateway:
 *
 * | Header | Default Value | Purpose |
 * |--------|--------------|---------|
 * | `Content-Security-Policy` | `default-src 'self'; ...` | XSS & injection prevention |
 * | `X-Frame-Options` | `DENY` | Clickjacking prevention |
 * | `X-Content-Type-Options` | `nosniff` | MIME sniffing prevention |
 * | `X-XSS-Protection` | `0` | Legacy XSS filter disabled (CSP is better) |
 * | `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer leakage prevention |
 * | `Permissions-Policy` | `camera=(), ...` | Browser API restriction |
 * | `Strict-Transport-Security` | `max-age=63072000; ...` | HTTPS enforcement (prod only) |
 * | `Cache-Control` | `no-store, no-cache, must-revalidate, private` | Sensitive data cache prevention |
 *
 * @returns A `Record<string, string>` of all default security headers.
 *
 * @example
 * ```ts
 * const headers = getDefaultSecurityHeaders();
 * // Apply all defaults
 * for (const [name, value] of Object.entries(headers)) {
 *   response.headers.set(name, value);
 * }
 * ```
 */
export function getDefaultSecurityHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    [SecurityHeaders.ContentSecurityPolicy]: createCspHeader(),
    [SecurityHeaders.FrameOptions]: 'DENY',
    [SecurityHeaders.ContentTypeOptions]: 'nosniff',
    [SecurityHeaders.XssProtection]: '0',
    [SecurityHeaders.ReferrerPolicy]: 'strict-origin-when-cross-origin',
    [SecurityHeaders.PermissionsPolicy]: DEFAULT_PERMISSIONS_POLICY,
    [SecurityHeaders.CacheControl]: 'no-store, no-cache, must-revalidate, private',
  };

  // HSTS is only added in production
  const hsts = getHstsHeader();
  if (hsts) {
    headers[SecurityHeaders.StrictTransportSecurity] = hsts;
  }

  return headers;
}

/**
 * Apply security headers to a Next.js response.
 *
 * Clones the given {@link NextResponse}, merges all default security
 * headers onto it, then applies any overrides from {@link SecurityHeaderOptions}.
 *
 * **Option processing order:**
 * 1. Apply all default security headers.
 * 2. If `cspOverrides` are provided, rebuild the CSP header with the
 *    overridden directives.
 * 3. If `disableHsts` is `true`, remove the HSTS header.
 * 4. If `customFrameOptions` is set, override `X-Frame-Options`.
 * 5. Remove any headers listed in `skipHeaders` (case-insensitive).
 * 6. Apply `additionalHeaders` last, allowing full override control.
 *
 * @param response - The original {@link NextResponse} to enhance.
 * @param opts     - Optional overrides. See {@link SecurityHeaderOptions}.
 * @returns A **new** {@link NextResponse} with security headers applied.
 *          The original response is never mutated.
 *
 * @example
 * ```ts
 * // Apply all defaults
 * const secureResponse = applySecurityHeaders(response);
 *
 * // With overrides
 * const secureResponse = applySecurityHeaders(response, {
 *   cspOverrides: { 'script-src': ["'self'", 'analytics.example.com'] },
 *   customFrameOptions: 'SAMEORIGIN',
 *   skipHeaders: ['Cache-Control'],
 *   additionalHeaders: { 'X-Request-ID': crypto.randomUUID() },
 * });
 * ```
 */
export function applySecurityHeaders(
  response: NextResponse,
  opts?: SecurityHeaderOptions
): NextResponse {
  // Clone the response to avoid mutating the original
  const newResponse = new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });

  // 1. Apply all default security headers
  const defaultHeaders = getDefaultSecurityHeaders();
  for (const [name, value] of Object.entries(defaultHeaders)) {
    newResponse.headers.set(name, value);
  }

  // 2. Apply CSP overrides if provided
  if (opts?.cspOverrides && Object.keys(opts.cspOverrides).length > 0) {
    const customCsp = createCspHeader(opts.cspOverrides);
    newResponse.headers.set(SecurityHeaders.ContentSecurityPolicy, customCsp);
  }

  // 3. Disable HSTS if requested (also ensures it's removed if somehow set in dev)
  if (opts?.disableHsts) {
    newResponse.headers.delete(SecurityHeaders.StrictTransportSecurity);
  }

  // 4. Custom frame options
  if (opts?.customFrameOptions) {
    newResponse.headers.set(SecurityHeaders.FrameOptions, opts.customFrameOptions);
  }

  // 5. Skip specified headers
  if (opts?.skipHeaders && opts.skipHeaders.length > 0) {
    const skipSet = new Set(
      opts.skipHeaders.map((h) => h.toLowerCase())
    );

    // Map of our constant names to their actual header names for deletion
    const headerNameMap: Record<string, string> = {
      [SecurityHeaders.ContentSecurityPolicy.toLowerCase()]:
        SecurityHeaders.ContentSecurityPolicy,
      [SecurityHeaders.FrameOptions.toLowerCase()]:
        SecurityHeaders.FrameOptions,
      [SecurityHeaders.ContentTypeOptions.toLowerCase()]:
        SecurityHeaders.ContentTypeOptions,
      [SecurityHeaders.XssProtection.toLowerCase()]:
        SecurityHeaders.XssProtection,
      [SecurityHeaders.ReferrerPolicy.toLowerCase()]:
        SecurityHeaders.ReferrerPolicy,
      [SecurityHeaders.PermissionsPolicy.toLowerCase()]:
        SecurityHeaders.PermissionsPolicy,
      [SecurityHeaders.StrictTransportSecurity.toLowerCase()]:
        SecurityHeaders.StrictTransportSecurity,
      [SecurityHeaders.CacheControl.toLowerCase()]:
        SecurityHeaders.CacheControl,
      [SecurityHeaders.RequestId.toLowerCase()]:
        SecurityHeaders.RequestId,
    };

    for (const skipName of skipSet) {
      const actualName = headerNameMap[skipName];
      if (actualName) {
        newResponse.headers.delete(actualName);
      }
    }
  }

  // 6. Apply additional custom headers last (can override defaults)
  if (opts?.additionalHeaders) {
    for (const [name, value] of Object.entries(opts.additionalHeaders)) {
      newResponse.headers.set(name, value);
    }
  }

  return newResponse;
}

// ─── Middleware Wrapper ──────────────────────────────────────────────

/**
 * Type describing a Next.js middleware or route handler that returns
 * a {@link NextResponse}.
 *
 * Compatible with Next.js App Router middleware, Edge functions, and
 * Express-style route handlers adapted for Next.js.
 */
export type SecurityHeadersHandler = (
  request: Request,
  ctx?: Record<string, unknown>
) => Promise<NextResponse> | NextResponse;

/**
 * Wrap a Next.js handler to automatically apply security headers to
 * every response it returns.
 *
 * This is the primary integration point for route-level security
 * headers. Wrap any handler that returns a {@link NextResponse} and
 * all responses will include the full G1+G2 security header set.
 *
 * **Behaviour:**
 * - If the handler returns a {@link NextResponse}, security headers
 *   are applied via {@link applySecurityHeaders}.
 * - If the handler throws, the error propagates untouched — security
 *   headers are only applied to successful responses. Use an upstream
 *   error handler to add headers to error responses.
 * - If the handler returns something other than a {@link NextResponse},
 *   it is passed through without modification.
 *
 * @param handler - The original handler to wrap.
 * @param opts    - Optional security header overrides applied to every
 *                  response from this handler. See {@link SecurityHeaderOptions}.
 * @returns A wrapped handler with identical signature that applies
 *          security headers to all responses.
 *
 * @example
 * ```ts
 * // Basic usage — apply all defaults
 * export const GET = withSecurityHeaders(async (request) => {
 *   return NextResponse.json({ status: 'ok' });
 * });
 *
 * // With custom options
 * export const GET = withSecurityHeaders(
 *   async (request) => {
 *     return NextResponse.json({ data: [] });
 *   },
 *   {
 *     cspOverrides: { 'img-src': ["'self'", 'data:', 'cdn.example.com'] },
 *     skipHeaders: ['Cache-Control'],
 *   }
 * );
 * ```
 */
export function withSecurityHeaders(
  handler: SecurityHeadersHandler,
  opts?: SecurityHeaderOptions
): SecurityHeadersHandler {
  return async (request: Request, ctx?: Record<string, unknown>): Promise<NextResponse> => {
    const result = await handler(request, ctx);

    // Only apply security headers to NextResponse instances
    if (result instanceof NextResponse) {
      return applySecurityHeaders(result, opts);
    }

    return result;
  };
}
