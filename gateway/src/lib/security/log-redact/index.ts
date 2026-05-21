/**
 * @module log-redact
 * @description Log redaction module that prevents sensitive data from appearing in logs.
 *
 * Provides utilities to redact API keys, tokens, passwords, emails, phone numbers,
 * credit card numbers, wallet addresses, IP addresses, JWTs, database connection strings,
 * and environment variable values from log output.
 *
 * @example
 * ```ts
 * import { redact, redactLogEntry, redactString, createRedactedLogger } from './log-redact';
 *
 * // Quick one-off redaction
 * const safe = redact('User sk_live_abc123 logged in from 192.168.1.50');
 * // => "User [REDACTED_API_KEY] logged in from 192.168.*.*"
 *
 * // Redact an entire log entry object
 * const entry = redactLogEntry({ user: 'bob', password: 's3cret', email: 'bob@test.com' });
 * // => { user: 'bob', password: '[REDACTED_PASSWORD]', email: '***@***.***' }
 *
 * // Wrap an existing logger so every call is automatically redacted
 * const logger = createRedactedLogger(console);
 * logger.info('apikey=sk_test_xyz token=Bearer abc123');
 * // => "apikey=[REDACTED_API_KEY] token=[REDACTED_BEARER]"
 * ```
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Names of the built-in sensitive-data pattern categories that the redactor
 * recognises.  Each name maps to an internal regex + replacement strategy.
 */
export type SensitivePatternName =
  | 'apiKey'
  | 'bearerToken'
  | 'password'
  | 'email'
  | 'phoneNumber'
  | 'creditCard'
  | 'walletAddress'
  | 'ipAddress'
  | 'jwt'
  | 'dbConnectionString'
  | 'envVariable';

/**
 * Configuration object that controls how the redactor behaves.
 */
export interface LogRedactionConfig {
  /**
   * Which built-in pattern categories to enable.
   * Defaults to **all** patterns when omitted or set to `undefined`.
   * Provide an explicit array to limit redaction to only those categories.
   */
  enabledPatterns?: SensitivePatternName[];

  /**
   * Single character used for masking when `preserveFormat` is `false` or
   * when a pattern does not define its own format-preserving replacement.
   * @default '*'
   */
  replacementChar?: string;

  /**
   * When `true`, the redactor attempts to preserve the visual format of the
   * original value (e.g. `***@***.***` for emails, `****-****-****-****`
   * for credit cards, `192.168.*.*` for IPs).  When `false`, values are
   * replaced with a generic tag like `[REDACTED_<CATEGORY>]`.
   * @default true
   */
  preserveFormat?: boolean;

  /**
   * Additional custom regex patterns to redact.  Each entry must provide:
   * - `name`  – a human-readable label used in the replacement tag.
   * - `regex` – a `RegExp` whose first capture group is the sensitive value.
   * - `replacement` – (optional) a format-preserving replacement string.
   *   If omitted the value is replaced with `[REDACTED_<name>]`.
   */
  customPatterns?: CustomRedactionPattern[];
}

/**
 * A user-defined redaction pattern that extends the built-in set.
 */
export interface CustomRedactionPattern {
  /** Human-readable label used in the `[REDACTED_<name>]` tag. */
  name: string;
  /**
   * Regular expression.  The first capture group is treated as the sensitive
   * value that should be redacted.
   */
  regex: RegExp;
  /** Optional format-preserving replacement string. */
  replacement?: string;
}

// ---------------------------------------------------------------------------
// Internal: pattern definitions
// ---------------------------------------------------------------------------

interface InternalPattern {
  name: SensitivePatternName;
  regex: RegExp;
  /** Replacement used when `preserveFormat` is true.  `$1` refers to first capture group where applicable. */
  preserveReplacement: string;
  /** Replacement used when `preserveFormat` is false. */
  tagReplacement: string;
}

/**
 * Master list of built-in sensitive-data patterns.
 * Order matters: more-specific patterns should come **before** more-general
 * ones to avoid partial overlaps (e.g. Bearer before generic API-key patterns).
 */
const BUILTIN_PATTERNS: InternalPattern[] = [
  // ---- API Keys -----------------------------------------------------------
  {
    name: 'apiKey',
    regex: /\b(sk_[\w-]{8,}|zk_[\w-]{8,}|key_[\w-]{8,}|api_key\s*=\s*([\w-]+)|apikey\s*=\s*([\w-]+))/gi,
    preserveReplacement: '[REDACTED_API_KEY]',
    tagReplacement: '[REDACTED_API_KEY]',
  },

  // ---- Bearer Tokens ------------------------------------------------------
  {
    name: 'bearerToken',
    regex: /\bBearer\s+[\w\-._~+/]+=*/gi,
    preserveReplacement: '[REDACTED_BEARER]',
    tagReplacement: '[REDACTED_BEARER]',
  },

  // ---- Passwords ----------------------------------------------------------
  {
    name: 'password',
    regex: /\b(?:password|passwd|pwd)\s*[=:]\s*([^\s,;}\]"']+)/gi,
    preserveReplacement: '[REDACTED_PASSWORD]',
    tagReplacement: '[REDACTED_PASSWORD]',
  },

  // ---- Email Addresses ----------------------------------------------------
  {
    name: 'email',
    regex: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
    preserveReplacement: '***@***.***',
    tagReplacement: '[REDACTED_EMAIL]',
  },

  // ---- Phone Numbers ------------------------------------------------------
  {
    name: 'phoneNumber',
    regex: /(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}\b/g,
    preserveReplacement: '***-***-****',
    tagReplacement: '[REDACTED_PHONE]',
  },

  // ---- Credit Card Numbers ------------------------------------------------
  {
    name: 'creditCard',
    regex: /\b(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})\b/g,
    preserveReplacement: '****-****-****-****',
    tagReplacement: '[REDACTED_CC]',
  },

  // ---- TRC20 / TRON Wallet Addresses (T-prefix, 34 chars) ----------------
  {
    name: 'walletAddress',
    regex: /\bT[A-Za-z0-9]{33}\b/g,
    preserveReplacement: 'T***...***',
    tagReplacement: '[REDACTED_WALLET]',
  },

  // ---- IP Addresses (IPv4) -----------------------------------------------
  {
    name: 'ipAddress',
    regex: /\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b/g,
    preserveReplacement: '$1.*.*.*',
    tagReplacement: '[REDACTED_IP]',
  },

  // ---- JWT Tokens ---------------------------------------------------------
  {
    name: 'jwt',
    regex: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
    preserveReplacement: 'eyJ***.eyJ***.***',
    tagReplacement: '[REDACTED_JWT]',
  },

  // ---- Database Connection Strings ----------------------------------------
  {
    name: 'dbConnectionString',
    regex: /\b(?:mongodb|postgres|postgresql|mysql|redis|mssql|sqlserver):\/\/[^\s'"}\]]+/gi,
    preserveReplacement: '[REDACTED_DB_CONN]',
    tagReplacement: '[REDACTED_DB_CONN]',
  },

  // ---- Environment Variable Values ----------------------------------------
  {
    name: 'envVariable',
    regex: /\b(?:ENV|env|ENVIRONMENT|environment|SECRET|secret|TOKEN|token|KEY|key|PASSWORD|password|CREDENTIAL|credential)\s*[=:]\s*([^\s,;}\]"']+)/gi,
    preserveReplacement: '[REDACTED_ENV]',
    tagReplacement: '[REDACTED_ENV]',
  },
];

// ---------------------------------------------------------------------------
// Default config
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: Required<Omit<LogRedactionConfig, 'enabledPatterns' | 'customPatterns'>> & {
  enabledPatterns: SensitivePatternName[];
  customPatterns: CustomRedactionPattern[];
} = {
  enabledPatterns: BUILTIN_PATTERNS.map((p) => p.name),
  replacementChar: '*',
  preserveFormat: true,
  customPatterns: [],
};

// ---------------------------------------------------------------------------
// Core helpers
// ---------------------------------------------------------------------------

/**
 * Merge a user-supplied partial config with the defaults.
 */
function resolveConfig(config?: LogRedactionConfig): Required<LogRedactionConfig> {
  return {
    enabledPatterns: config?.enabledPatterns ?? DEFAULT_CONFIG.enabledPatterns,
    replacementChar: config?.replacementChar ?? DEFAULT_CONFIG.replacementChar,
    preserveFormat: config?.preserveFormat ?? DEFAULT_CONFIG.preserveFormat,
    customPatterns: config?.customPatterns ?? DEFAULT_CONFIG.customPatterns,
  };
}

/**
 * Apply a single built-in pattern to a string and return the redacted result.
 */
function applyBuiltinPattern(
  input: string,
  pattern: InternalPattern,
  config: Required<LogRedactionConfig>,
): string {
  const replacement = config.preserveFormat ? pattern.preserveReplacement : pattern.tagReplacement;
  // Clone regex to avoid mutating lastIndex on shared instances
  const regex = new RegExp(pattern.regex.source, pattern.regex.flags);
  return input.replace(regex, replacement);
}

/**
 * Apply a custom pattern to a string and return the redacted result.
 */
function applyCustomPattern(
  input: string,
  custom: CustomRedactionPattern,
  config: Required<LogRedactionConfig>,
): string {
  const replacement =
    config.preserveFormat && custom.replacement
      ? custom.replacement
      : `[REDACTED_${custom.name.toUpperCase()}]`;
  const regex = new RegExp(custom.regex.source, custom.regex.flags);
  return input.replace(regex, replacement);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Redact sensitive patterns in a raw string.
 *
 * Scans the input for all enabled sensitive-data patterns and replaces each
 * match with either a format-preserving mask or a generic `[REDACTED_*]` tag,
 * depending on the `preserveFormat` config option.
 *
 * @param input  - The string to sanitise.
 * @param config - Optional redaction configuration.
 * @returns The redacted string with sensitive values replaced.
 *
 * @example
 * ```ts
 * redactString('Bearer abc123');
 * // => '[REDACTED_BEARER]'
 *
 * redactString('email=user@example.com', { preserveFormat: false });
 * // => 'email=[REDACTED_EMAIL]'
 * ```
 */
export function redactString(input: string, config?: LogRedactionConfig): string {
  const resolved = resolveConfig(config);

  let result = input;

  // Apply enabled built-in patterns
  for (const pattern of BUILTIN_PATTERNS) {
    if (resolved.enabledPatterns.includes(pattern.name)) {
      result = applyBuiltinPattern(result, pattern, resolved);
    }
  }

  // Apply custom patterns
  for (const custom of resolved.customPatterns) {
    result = applyCustomPattern(result, custom, resolved);
  }

  return result;
}

/**
 * Recursively redact sensitive values in a log-entry object.
 *
 * Walks the object depth-first.  For each **string** value the same
 * pattern-matching logic as {@link redactString} is applied.  Non-string
 * primitive values are left untouched.  Arrays and nested objects are
 * traversed recursively.
 *
 * The input object is **not** mutated; a shallow-deep clone is returned.
 *
 * @param entry  - The log entry to redact.
 * @param config - Optional redaction configuration.
 * @returns A new object with sensitive values redacted.
 *
 * @example
 * ```ts
 * redactLogEntry({
 *   user: 'alice',
 *   password: 's3cret',
 *   meta: { token: 'Bearer xyz' },
 * });
 * // => { user: 'alice', password: '[REDACTED_PASSWORD]', meta: { token: '[REDACTED_BEARER]' } }
 * ```
 */
export function redactLogEntry(
  entry: Record<string, unknown>,
  config?: LogRedactionConfig,
): Record<string, unknown> {
  const resolved = resolveConfig(config);

  const redactValue = (value: unknown): unknown => {
    if (typeof value === 'string') {
      return redactString(value, resolved);
    }
    if (Array.isArray(value)) {
      return value.map(redactValue);
    }
    if (value !== null && typeof value === 'object') {
      const obj: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        obj[k] = redactValue(v);
      }
      return obj;
    }
    return value;
  };

  const result: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(entry)) {
    result[key] = redactValue(val);
  }
  return result;
}

// ---------------------------------------------------------------------------
// createRedactedLogger
// ---------------------------------------------------------------------------

/** Subset of console methods we wrap for redaction. */
type ConsoleMethod = 'log' | 'info' | 'warn' | 'error' | 'debug' | 'trace';

const CONSOLE_METHODS: ConsoleMethod[] = ['log', 'info', 'warn', 'error', 'debug', 'trace'];

/**
 * Create a wrapped console logger that automatically redacts all arguments
 * before forwarding them to the underlying logger.
 *
 * Each argument is processed independently:
 * - **strings** are passed through {@link redactString}
 * - **plain objects** are passed through {@link redactLogEntry}
 * - all other values (numbers, booleans, `null`, `undefined`, Errors, etc.)
 *   are forwarded unchanged.
 *
 * @param logger - The underlying console-like object to wrap (e.g. the global `console`).
 * @param config - Optional redaction configuration.
 * @returns A console-like object whose logging methods auto-redact their arguments.
 *
 * @example
 * ```ts
 * const logger = createRedactedLogger(console);
 * logger.info('apikey=sk_live_abc123', { user: 'bob@example.com' });
 * // Console output: "apikey=[REDACTED_API_KEY]" { user: '***@***.***' }
 * ```
 */
export function createRedactedLogger(
  logger: Console,
  config?: LogRedactionConfig,
): Record<ConsoleMethod, (...args: unknown[]) => void> & Record<string, unknown> {
  const resolved = resolveConfig(config);

  const wrapped: Record<string, unknown> = {};

  for (const method of CONSOLE_METHODS) {
    wrapped[method] = (...args: unknown[]): void => {
      const redactedArgs = args.map((arg) => {
        if (typeof arg === 'string') {
          return redactString(arg, resolved);
        }
        if (arg !== null && typeof arg === 'object' && !Array.isArray(arg) && !(arg instanceof Error)) {
          return redactLogEntry(arg as Record<string, unknown>, resolved);
        }
        if (Array.isArray(arg)) {
          return arg.map((item) => {
            if (typeof item === 'string') return redactString(item, resolved);
            if (item !== null && typeof item === 'object' && !(item instanceof Error)) {
              return redactLogEntry(item as Record<string, unknown>, resolved);
            }
            return item;
          });
        }
        return arg;
      });

      const fn = logger[method] as (...a: unknown[]) => void;
      if (typeof fn === 'function') {
        fn.apply(logger, redactedArgs);
      }
    };
  }

  // Proxy any other console properties (e.g. `assert`, `table`) straight through
  return new Proxy(wrapped as Record<ConsoleMethod, (...args: unknown[]) => void> & Record<string, unknown>, {
    get(target, prop: string) {
      if (prop in target) {
        return target[prop];
      }
      return (logger as Record<string, unknown>)[prop];
    },
  });
}

// ---------------------------------------------------------------------------
// Default export – quick-use function
// ---------------------------------------------------------------------------

/**
 * Quick-use redaction function.  Accepts either a **string** or a **log-entry
 * object** and returns the redacted result.
 *
 * This is the easiest way to drop redaction into existing code:
 *
 * @example
 * ```ts
 * import redact from './log-redact';
 *
 * console.log(redact('Bearer abc123'));
 * // => "[REDACTED_BEARER]"
 *
 * console.log(redact({ password: 's3cret' }));
 * // => { password: '[REDACTED_PASSWORD]' }
 * ```
 *
 * @param input  - A string or object to redact.
 * @param config - Optional redaction configuration.
 * @returns The redacted string or object.
 */
function redact(input: string, config?: LogRedactionConfig): string;
function redact(input: Record<string, unknown>, config?: LogRedactionConfig): Record<string, unknown>;
function redact(
  input: string | Record<string, unknown>,
  config?: LogRedactionConfig,
): string | Record<string, unknown> {
  if (typeof input === 'string') {
    return redactString(input, config);
  }
  return redactLogEntry(input, config);
}

export default redact;

// ---------------------------------------------------------------------------
// Re-export convenience
// ---------------------------------------------------------------------------

/**
 * Full set of built-in pattern names.  Useful when building an
 * `enabledPatterns` array dynamically.
 *
 * @example
 * ```ts
 * import { ALL_PATTERN_NAMES, redactString } from './log-redact';
 *
 * // Enable everything except IP addresses
 * const enabled = ALL_PATTERN_NAMES.filter((n) => n !== 'ipAddress');
 * redactString(text, { enabledPatterns: enabled });
 * ```
 */
export const ALL_PATTERN_NAMES: SensitivePatternName[] = BUILTIN_PATTERNS.map((p) => p.name);
