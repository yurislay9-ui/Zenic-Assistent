/**
 * @module security/error-handler
 * @description Secure error handler for the Zenic-Agents gateway.
 *
 * Prevents information leakage by sanitizing errors before they reach clients.
 * Strips stack traces, file paths, connection strings, internal variable names,
 * Prisma query details, IP addresses, and environment variable names/values.
 *
 * All outbound error responses are structured, correlation-tagged, and
 * free of implementation details that could aid an attacker.
 */

import { NextResponse } from "next/server";
import { randomUUID } from "crypto";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Shape of the JSON body returned by {@link createErrorResponse}.
 */
export interface SanitizedErrorResponse {
  /** `false` – always present so callers can check programmatically. */
  success: false;
  /** Human-readable, safe message. */
  error: string;
  /** Machine-readable error code (e.g. `"VALIDATION_ERROR"`). */
  code: string;
  /** HTTP status code mirrored for convenience. */
  statusCode: number;
  /** UUID linking server logs to this specific error occurrence. */
  correlationId: string;
  /** Additional safe details (only populated in development). */
  details?: Record<string, unknown>;
}

/**
 * Internal representation used while converting a raw error into a safe form.
 */
interface NormalizedError {
  message: string;
  statusCode: number;
  code: string;
  details?: Record<string, unknown>;
}

/**
 * Options accepted by {@link createErrorResponse}.
 */
export interface ErrorResponseOptions {
  /** Override the HTTP status code (defaults to 500 for unknown errors). */
  statusCode?: number;
  /** Override the machine-readable error code. */
  code?: string;
}

// ---------------------------------------------------------------------------
// Error-code constants
// ---------------------------------------------------------------------------

/** Machine-readable error codes for consistent API responses. */
export const ErrorCodes = {
  /** Request body or parameters failed validation. */
  VALIDATION_ERROR: "VALIDATION_ERROR",
  /** Authentication is required but was not provided. */
  AUTH_REQUIRED: "AUTH_REQUIRED",
  /** Authenticated user lacks permission for the requested resource. */
  FORBIDDEN: "FORBIDDEN",
  /** The requested resource was not found. */
  NOT_FOUND: "NOT_FOUND",
  /** A conflict prevents the operation (e.g. duplicate key). */
  CONFLICT: "CONFLICT",
  /** Rate-limit has been exceeded. */
  RATE_LIMITED: "RATE_LIMITED",
  /** An unexpected internal error occurred. */
  INTERNAL_ERROR: "INTERNAL_ERROR",
} as const;

/** Type alias derived from {@link ErrorCodes}. */
export type ErrorCode = (typeof ErrorCodes)[keyof typeof ErrorCodes];

// ---------------------------------------------------------------------------
// ErrorSanitizer – static utility class
// ---------------------------------------------------------------------------

/**
 * `ErrorSanitizer` provides pure, stateless helpers that strip potentially
 * sensitive information from error messages.
 *
 * Every method accepts a `string` and returns a sanitized `string` with
 * dangerous patterns replaced by safe placeholders.
 *
 * @example
 * ```ts
 * ErrorSanitizer.stripConnectionStrings(
 *   "connect ECONNREFUSED postgresql://admin:s3cret@db.internal:5432/prod"
 * );
 * // => "connect ECONNREFUSED [DB_URL]"
 * ```
 */
export class ErrorSanitizer {
  // -----------------------------------------------------------------------
  // Regex patterns (compiled once, reused on every call)
  // -----------------------------------------------------------------------

  /** Matches POSIX and Windows absolute/relative file paths. */
  private static readonly FILE_PATH_RE =
    /(?:^|[\s('"=])(?:(?:\/[\w.-]+){2,}|(?:[A-Za-z]:\\[\w.-]+(?:\\[\w.-]+)*))(?=[\s'"`),;]|$)/g;

  /** Matches common database / cache connection-string prefixes. */
  private static readonly CONNECTION_STRING_RE =
    /(?:postgres(?:ql)?|mysql|mongo(?:db)?|redis|mssql|sqlite|cockroachdb)(?:\+\w+)?:(?:\/\/)?[^\s'"`,;)]+/gi;

  /** Matches environment-variable references such as `API_KEY=value` or `${VAR}`. */
  private static readonly ENV_VAR_RE =
    /(?:^|[\s"'=])(?:[A-Z_][A-Z0-9_]{1,})(?:\s*=\s*[^\s'"`,;)]+|\})/g;

  /** Matches IPv4 addresses (loose – avoids false positives on version strings). */
  private static readonly IPV4_RE =
    /(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)/g;

  /** Matches IPv6 addresses (compressed and full forms). */
  private static readonly IPV6_RE =
    /(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}|::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}/g;

  /** Matches Prisma-specific error noise (model names, query fragments). */
  private static readonly PRISMA_MODEL_RE =
    /(?:Model|Table|prisma)\s+["']?\w+["']?/gi;

  /** Matches Prisma query-preview fragments. */
  private static readonly PRISMA_QUERY_RE =
    /(?:prisma|Prisma).*?(?:query|execute|findMany|findUnique|findFirst|create|update|delete|upsert).*?(?:\{[\s\S]*?\}|$)/gi;

  /** Matches common internal module / package paths in stack lines. */
  private static readonly MODULE_NAME_RE =
    /(?:node_modules|dist|src|lib)[/\\][\w./\\-]+/g;

  // -----------------------------------------------------------------------
  // Public static methods
  // -----------------------------------------------------------------------

  /**
   * Replace file-system paths with `[PATH]`.
   *
   * Handles both POSIX (`/usr/local/bin/app`) and Windows
   * (`C:\Users\admin\file.txt`) style paths.
   *
   * @param message - Raw error message that may contain file paths.
   * @returns The message with all file-path occurrences replaced by `[PATH]`.
   */
  static stripFilePaths(message: string): string {
    return message
      .replace(ErrorSanitizer.FILE_PATH_RE, (match) => {
        // Preserve the leading whitespace / quote character if captured
        const prefix = match.match(/^[\s'"=]/)?.[0] ?? "";
        return `${prefix}[PATH]`;
      })
      .replace(ErrorSanitizer.MODULE_NAME_RE, "[MODULE]");
  }

  /**
   * Replace database / cache connection strings with `[DB_URL]`.
   *
   * Covers PostgreSQL, MySQL, MongoDB, Redis, MSSQL, SQLite, CockroachDB,
   * and any Prisma-compatible protocol prefixes (e.g. `postgresql+pool://`).
   *
   * @param message - Raw error message that may contain connection strings.
   * @returns The message with all connection-string occurrences replaced by `[DB_URL]`.
   */
  static stripConnectionStrings(message: string): string {
    return message.replace(ErrorSanitizer.CONNECTION_STRING_RE, "[DB_URL]");
  }

  /**
   * Replace environment variable patterns with `[ENV_VAR]`.
   *
   * Catches `KEY=value` assignments and `${KEY}` template references.
   * Only targets UPPER_SNAKE_CASE identifiers (3+ chars) to avoid
   * false positives on ordinary words.
   *
   * @param message - Raw error message that may contain env-var references.
   * @returns The message with all env-var occurrences replaced by `[ENV_VAR]`.
   */
  static stripEnvVars(message: string): string {
    return message.replace(ErrorSanitizer.ENV_VAR_RE, (match) => {
      const prefix = match.match(/^[\s"'=]/)?.[0] ?? "";
      return `${prefix}[ENV_VAR]`;
    });
  }

  /**
   * Replace IPv4 and IPv6 addresses with `[IP]`.
   *
   * @param message - Raw error message that may contain IP addresses.
   * @returns The message with all IP-address occurrences replaced by `[IP]`.
   */
  static stripIPAddresses(message: string): string {
    return message
      .replace(ErrorSanitizer.IPV4_RE, "[IP]")
      .replace(ErrorSanitizer.IPV6_RE, "[IP]");
  }

  /**
   * Replace Prisma-specific error details with a generic message.
   *
   * Strips model names, query fragments, and internal Prisma identifiers
   * that could reveal schema or query structure to an attacker.
   *
   * @param message - Raw error message that may contain Prisma details.
   * @returns The message with Prisma-specific noise replaced by
   *          `[PRISMA_DETAILS]` or a fully generic fallback.
   */
  static stripPrismaDetails(message: string): string {
    let sanitized = message;

    // Replace Prisma model / table references
    sanitized = sanitized.replace(
      ErrorSanitizer.PRISMA_MODEL_RE,
      "[PRISMA_DETAILS]"
    );

    // Replace Prisma query fragments
    sanitized = sanitized.replace(
      ErrorSanitizer.PRISMA_QUERY_RE,
      "[PRISMA_DETAILS]"
    );

    // If the entire message was Prisma noise, return a generic statement
    if (/^\[PRISMA_DETAILS\](?:\s*\[PRISMA_DETAILS\])*$/.test(sanitized)) {
      return "A database operation failed";
    }

    return sanitized;
  }

  /**
   * Run **all** sanitization passes in the recommended order.
   *
   * Order matters: connection strings are stripped before env vars so that
   * embedded credentials inside connection strings are not partially leaked.
   *
   * @param message - Raw error message.
   * @returns Fully sanitized message safe for external consumption.
   */
  static sanitizeAll(message: string): string {
    let result = message;
    result = ErrorSanitizer.stripConnectionStrings(result);
    result = ErrorSanitizer.stripEnvVars(result);
    result = ErrorSanitizer.stripFilePaths(result);
    result = ErrorSanitizer.stripIPAddresses(result);
    result = ErrorSanitizer.stripPrismaDetails(result);
    return result;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Determine whether the current runtime is a development environment.
 *
 * Checks `process.env.NODE_ENV` — any value other than `"production"` is
 * treated as development so that preview / staging environments also benefit
 * from richer (but still sanitized) messages.
 */
function isDevelopment(): boolean {
  return process.env.NODE_ENV !== "production";
}

/**
 * Map a Prisma error code to a safe, user-facing message.
 *
 * Prisma throws `PrismaClientKnownRequestError` with a `code` property like
 * `"P2002"`. This function converts those codes into generic descriptions.
 *
 * @param code - The Prisma error code (e.g. `"P2002"`).
 * @returns A safe, human-readable message.
 */
function mapPrismaCode(code: string): { message: string; statusCode: number } {
  const prismaCodeMap: Record<string, { message: string; statusCode: number }> = {
    P2002: { message: "A unique constraint was violated", statusCode: 409 },
    P2003: { message: "A foreign key constraint failed", statusCode: 400 },
    P2025: { message: "The requested record was not found", statusCode: 404 },
    P2014: { message: "A required relation is missing", statusCode: 400 },
    P2001: { message: "The requested record does not exist", statusCode: 404 },
    P2016: { message: "Query interpretation error", statusCode: 400 },
    P2021: { message: "The table does not exist", statusCode: 500 },
    P2022: { message: "The column does not exist", statusCode: 500 },
  };

  return (
    prismaCodeMap[code] ?? {
      message: "A database operation failed",
      statusCode: 500,
    }
  );
}

/**
 * Attempt to extract a safe, user-facing message from a known error shape.
 *
 * Recognises:
 * - Native `Error` (and subclasses)
 * - Prisma `PrismaClientKnownRequestError` (via duck-typing on `code` /
 *   `meta` and `clientVersion`)
 * - Prisma `PrismaClientValidationError`
 * - Objects with a `message` property
 * - Strings
 * - Anything else → fallback
 *
 * @param error - The raw thrown value.
 * @returns A {@link NormalizedError} with safe message, status code, and code.
 */
function normalizeError(error: unknown): NormalizedError {
  // --- Prisma known request error (duck-typed) ---
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof (error as Record<string, unknown>).code === "string" &&
    (error as Record<string, unknown>).code.startsWith("P") &&
    "clientVersion" in error
  ) {
    const prismaErr = error as {
      code: string;
      message: string;
      meta?: Record<string, unknown>;
      clientVersion: string;
    };

    const mapped = mapPrismaCode(prismaErr.code);
    return {
      message: mapped.message,
      statusCode: mapped.statusCode,
      code:
        mapped.statusCode === 409
          ? ErrorCodes.CONFLICT
          : mapped.statusCode === 404
            ? ErrorCodes.NOT_FOUND
            : mapped.statusCode === 400
              ? ErrorCodes.VALIDATION_ERROR
              : ErrorCodes.INTERNAL_ERROR,
      details: isDevelopment()
        ? {
            prismaCode: prismaErr.code,
            sanitizedMessage: ErrorSanitizer.sanitizeAll(prismaErr.message),
          }
        : undefined,
    };
  }

  // --- Prisma validation error (duck-typed) ---
  if (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as Record<string, unknown>).name === "PrismaClientValidationError"
  ) {
    return {
      message: "Invalid request data provided",
      statusCode: 400,
      code: ErrorCodes.VALIDATION_ERROR,
      details: isDevelopment()
        ? {
            sanitizedMessage: ErrorSanitizer.sanitizeAll(
              (error as Error).message
            ),
          }
        : undefined,
    };
  }

  // --- Standard Error / subclass ---
  if (error instanceof Error) {
    // Detect common HTTP-error shapes ----------------------------------
    // Next.js / http-errors style: .statusCode or .status
    const httpStatus =
      "statusCode" in error
        ? (error as { statusCode: number }).statusCode
        : "status" in error
          ? (error as { status: number }).status
          : undefined;

    // JWT / auth errors
    if (
      error.name === "JsonWebTokenError" ||
      error.name === "TokenExpiredError" ||
      error.name === "NotBeforeError"
    ) {
      return {
        message: "Authentication failed",
        statusCode: 401,
        code: ErrorCodes.AUTH_REQUIRED,
      };
    }

    // Validation errors (class-validator, zod, joi, etc.)
    if (
      error.name === "ValidationError" ||
      error.name === "ZodError" ||
      error.name === "ValidatorError"
    ) {
      return {
        message: "Request validation failed",
        statusCode: 400,
        code: ErrorCodes.VALIDATION_ERROR,
        details: isDevelopment()
          ? {
              sanitizedMessage: ErrorSanitizer.sanitizeAll(error.message),
            }
          : undefined,
      };
    }

    // Syntax errors from JSON parsing
    if (error.name === "SyntaxError" && "status" in error === false) {
      return {
        message: "Invalid request format",
        statusCode: 400,
        code: ErrorCodes.VALIDATION_ERROR,
      };
    }

    // If the error already carries a meaningful HTTP status, honour it
    if (httpStatus && httpStatus >= 400 && httpStatus < 600) {
      const safeCode = httpStatusToErrorCode(httpStatus);
      return {
        message: httpStatusToSafeMessage(httpStatus),
        statusCode: httpStatus,
        code: safeCode,
      };
    }

    // Generic Error – treat as internal; never expose .message in production
    return {
      message: isDevelopment()
        ? ErrorSanitizer.sanitizeAll(error.message)
        : "An internal error occurred",
      statusCode: 500,
      code: ErrorCodes.INTERNAL_ERROR,
    };
  }

  // --- String ---
  if (typeof error === "string") {
    return {
      message: isDevelopment()
        ? ErrorSanitizer.sanitizeAll(error)
        : "An internal error occurred",
      statusCode: 500,
      code: ErrorCodes.INTERNAL_ERROR,
    };
  }

  // --- Object with a `message` key ---
  if (typeof error === "object" && error !== null && "message" in error) {
    const msg = String((error as Record<string, unknown>).message);
    return {
      message: isDevelopment()
        ? ErrorSanitizer.sanitizeAll(msg)
        : "An internal error occurred",
      statusCode: 500,
      code: ErrorCodes.INTERNAL_ERROR,
    };
  }

  // --- Fallback: totally unknown ---
  return {
    message: "An internal error occurred",
    statusCode: 500,
    code: ErrorCodes.INTERNAL_ERROR,
  };
}

/**
 * Convert an HTTP status code into a safe, user-facing message.
 *
 * Only non-500 codes receive specific messaging; 500-class errors always
 * return a generic string.
 *
 * @param statusCode - HTTP status code.
 * @returns A safe message.
 */
function httpStatusToSafeMessage(statusCode: number): string {
  const messages: Record<number, string> = {
    400: "Invalid request",
    401: "Authentication required",
    403: "Access denied",
    404: "Resource not found",
    409: "A conflict occurred with the current state",
    422: "Unable to process the request data",
    429: "Too many requests – please try again later",
  };

  if (statusCode >= 500) return "An internal error occurred";
  return messages[statusCode] ?? "An error occurred";
}

/**
 * Map an HTTP status code to the most appropriate {@link ErrorCode}.
 *
 * @param statusCode - HTTP status code.
 * @returns A matching error-code constant.
 */
function httpStatusToErrorCode(statusCode: number): ErrorCode {
  const map: Record<number, ErrorCode> = {
    400: ErrorCodes.VALIDATION_ERROR,
    401: ErrorCodes.AUTH_REQUIRED,
    403: ErrorCodes.FORBIDDEN,
    404: ErrorCodes.NOT_FOUND,
    409: ErrorCodes.CONFLICT,
    429: ErrorCodes.RATE_LIMITED,
  };

  if (statusCode >= 500) return ErrorCodes.INTERNAL_ERROR;
  return map[statusCode] ?? ErrorCodes.INTERNAL_ERROR;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Convert any thrown value into a safe, sanitized error response object.
 *
 * In **production**, internal details (stack traces, raw messages, Prisma
 * codes, etc.) are never included. In **development**, additional context is
 * attached but still passes through every {@link ErrorSanitizer} pass to
 * prevent accidental secret leakage.
 *
 * @param error - The raw error thrown anywhere in the gateway.
 * @returns A {@link SanitizedErrorResponse} that is safe to return to clients.
 *
 * @example
 * ```ts
 * try {
 *   await prisma.user.findUniqueOrThrow({ where: { id } });
 * } catch (err) {
 *   return sanitizeError(err);
 * }
 * ```
 */
export function sanitizeError(error: unknown): SanitizedErrorResponse {
  const normalized = normalizeError(error);
  const correlationId = randomUUID();

  return {
    success: false,
    error: normalized.message,
    code: normalized.code,
    statusCode: normalized.statusCode,
    correlationId,
    ...(normalized.details && { details: normalized.details }),
  };
}

/**
 * Create a `NextResponse` containing a sanitized JSON error body.
 *
 * This is the primary entry-point for API route handlers. It:
 * 1. Normalises the error via {@link normalizeError}.
 * 2. Sanitizes every string that might reach the client.
 * 3. Attaches a correlation-ID (UUID v4) for log correlation.
 * 4. In development, appends a `details` object (still sanitized).
 * 5. Sets appropriate security headers.
 *
 * @param error   - The raw error thrown in the route handler.
 * @param opts    - Optional overrides for status code and error code.
 * @returns A `NextResponse` ready to be returned from a Next.js API route.
 *
 * @example
 * ```ts
 * // app/api/users/route.ts
 * export async function GET(request: Request) {
 *   try {
 *     const users = await listUsers();
 *     return NextResponse.json(users);
 *   } catch (err) {
 *     return createErrorResponse(err);
 *   }
 * }
 * ```
 *
 * @example
 * ```ts
 * // With explicit overrides
 * return createErrorResponse(new Error("boom"), {
 *   statusCode: 429,
 *   code: ErrorCodes.RATE_LIMITED,
 * });
 * ```
 */
export function createErrorResponse(
  error: unknown,
  opts?: ErrorResponseOptions
): NextResponse<SanitizedErrorResponse> {
  const normalized = normalizeError(error);
  const correlationId = randomUUID();

  // Allow callers to override the detected status / code
  const statusCode = opts?.statusCode ?? normalized.statusCode;
  const code = opts?.code ?? normalized.code;

  // Determine the user-facing message
  let userMessage: string;
  if (statusCode >= 500) {
    // NEVER expose internal details for server errors in production
    userMessage = "An internal error occurred";
  } else {
    userMessage = httpStatusToSafeMessage(statusCode);
  }

  const body: SanitizedErrorResponse = {
    success: false,
    error: userMessage,
    code,
    statusCode,
    correlationId,
    ...(isDevelopment() && {
      details: {
        ...normalized.details,
        // In dev mode, include the sanitized raw message for debugging
        ...(normalized.message !== userMessage && {
          debugMessage: ErrorSanitizer.sanitizeAll(normalized.message),
        }),
      },
    }),
  };

  // Log internally with full context (never returned to the client)
  if (isDevelopment()) {
    console.error(
      `[ErrorHandler] correlationId=${correlationId} statusCode=${statusCode} code=${code}`,
      error
    );
  } else {
    // In production, log a structured line without the full error object
    // (which might contain secrets). The correlation ID lets operators
    // cross-reference with more verbose internal logs.
    console.error(
      JSON.stringify({
        level: "error",
        correlationId,
        statusCode,
        code,
        timestamp: new Date().toISOString(),
      })
    );
  }

  const response = NextResponse.json(body, { status: statusCode });

  // Security headers
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Correlation-Id", correlationId);
  // Prevent caching of error responses
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate");
  response.headers.set("Pragma", "no-cache");

  return response;
}
