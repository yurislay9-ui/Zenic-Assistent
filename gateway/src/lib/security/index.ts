/**
 * Zenic-Agents Security Module — Barrel Export
 *
 * Centralizes all security sub-modules for convenient imports:
 *
 *   import { sanitizeSearchParams, AuditLogger, createErrorResponse, ... } from '@/lib/security';
 *
 * FASE 3 - Modules:
 * - sanitize:     Query param & input sanitization (#20)
 * - error-handler: Sanitized error responses (#31)
 * - audit:        Structured audit logging (#32)
 * - session:      Session lifecycle management (#37)
 * - log-redact:   Sensitive data redaction in logs (#33)
 * - config:       Secure-by-default configuration (#34)
 * - headers:      Security headers (CSP, HSTS, etc.) (G2)
 * - config/integrity: Dependency & env integrity checks (G3)
 */

// ─── Sanitize (#20) ──────────────────────────────────────────────────
export {
  sanitizeSearchParams,
  validatePathParam,
  sanitizeString,
  detectSqlInjection,
  detectXss,
  detectPathTraversal,
  withSanitizedParams,
  SanitizationError,
  DEFAULT_PARAM_SPEC,
} from "./sanitize";

export type {
  PathParamType,
  SanitizeStringOptions,
  ThreatDetectionResult,
  SanitizedRequest,
  RouteContext,
  RouteHandler,
  ParamValidationSpec,
} from "./sanitize";

// ─── Error Handler (#31) ─────────────────────────────────────────────
export {
  sanitizeError,
  createErrorResponse,
  ErrorSanitizer,
  ErrorCodes,
} from "./error-handler";

export type {
  SanitizedErrorResponse,
  ErrorResponseOptions,
  ErrorCode,
} from "./error-handler";

// ─── Audit Logging (#32) ────────────────────────────────────────────
export {
  AuditLogger,
  auditHITLDecision,
  auditSubscriptionChange,
  auditPaymentAction,
  withAuditLog,
} from "./audit";

export type {
  AuditEvent,
  AuditEventType,
  AuditResult,
  AuditSeverity,
} from "./audit";

// ─── Session Management (#37) ────────────────────────────────────────
export {
  SessionManager,
  withSessionValidation,
  getSessionManager,
  DEFAULT_SESSION_CONFIG,
} from "./session";

export type {
  Session,
  SessionMetadata,
  SessionConfig,
} from "./session";

// ─── Log Redaction (#33) ─────────────────────────────────────────────
export {
  redactString,
  redactLogEntry,
  createRedactedLogger,
  ALL_PATTERN_NAMES,
} from "./log-redact";

export type {
  LogRedactionConfig,
  CustomRedactionPattern,
  SensitivePatternName,
} from "./log-redact";

// ─── Secure Config (#34) ────────────────────────────────────────────
export {
  SecurityConfig,
  INSECURE_DEFAULTS,
  loadSecurityConfig,
  validateSecurityConfig,
} from "./config";

export type {
  SecurityConfigType,
  SecurityConfigValidationResult,
  RateLimitTier,
  CorsConfig,
  RateLimitConfig,
  AuditConfig,
  SanitizeConfig,
  HeadersConfig,
  EncryptionConfig,
  AuthConfig,
} from "./config";

// ─── Security Headers (G2) ──────────────────────────────────────────
export {
  SecurityHeaders,
  getDefaultSecurityHeaders,
  applySecurityHeaders as applySecurityHeadersLib,
  createCspHeader,
  getHstsHeader,
  withSecurityHeaders,
} from "./headers";

export type {
  SecurityHeaderOptions,
} from "./headers";

// ─── Dependency Integrity (G3) ──────────────────────────────────────
export {
  DependencyIntegrityChecker,
  INSECURE_VALUES,
  runStartupIntegrityCheck,
} from "./config/integrity";

export type {
  IntegrityReport,
  EnvIntegrityReport,
  FullIntegrityReport,
  IntegrityStatus,
  EnvIntegrityStatus,
  OverallIntegrityStatus,
} from "./config/integrity";
