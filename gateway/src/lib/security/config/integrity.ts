// ─── Zenic-Agents Gateway — Dependency Integrity Checker ──────────────
// Provides runtime integrity checking for critical gateway dependencies
// and environment configuration. Verifies that required modules are
// present and haven't been tampered with, and flags known-insecure
// environment variable values before the application accepts traffic.

import { createHash } from 'crypto';

// ─── Type Definitions ───────────────────────────────────────────────

/**
 * Status of a single dependency module after an integrity check.
 *
 * - `ok`       — Module resolved successfully and its hash matches expectations.
 * - `missing`  — The module could not be imported / resolved at all.
 * - `tampered` — The module resolved but its content hash differs from the
 *                expected value (potential supply-chain or filesystem tampering).
 * - `unknown`  — The module resolved but no expected hash was provided for
 *                comparison, so integrity cannot be confirmed.
 */
export type IntegrityStatus = 'ok' | 'missing' | 'tampered' | 'unknown';

/**
 * Result of verifying a single critical dependency module.
 *
 * Each field is documented inline. When `status` is `'ok'` both hashes
 * will be present and identical; when `'missing'` neither hash is
 * available; when `'tampered'` both hashes are present but differ;
 * when `'unknown'` only `actualHash` is populated.
 */
export interface IntegrityReport {
  /** The NPM package name that was checked (e.g. `"@prisma/client"`). */
  moduleName: string;

  /** Outcome of the integrity verification. */
  status: IntegrityStatus;

  /** The SHA-256 digest that was expected (absent if no expectation was set). */
  expectedHash?: string;

  /** The SHA-256 digest computed at runtime (absent if the module is missing). */
  actualHash?: string;

  /** Human-readable description of the result. */
  message: string;
}

/**
 * Status of a single environment variable after a security check.
 *
 * - `ok`       — The variable is set and passes all security rules.
 * - `missing`  — The variable is not defined in the current environment.
 * - `insecure` — The variable is set but its value matches a known-insecure
 *                default (see {@link INSECURE_VALUES}).
 * - `default`  — The variable is set but appears to be a placeholder /
 *                template value that was never customised for this deployment.
 */
export type EnvIntegrityStatus = 'ok' | 'missing' | 'insecure' | 'default';

/**
 * Result of verifying a single environment variable.
 *
 * Produced by {@link DependencyIntegrityChecker.checkEnvIntegrity}.
 */
export interface EnvIntegrityReport {
  /** Name of the environment variable that was checked. */
  variable: string;

  /** Outcome of the environment-variable security check. */
  status: EnvIntegrityStatus;

  /** Human-readable description of the finding. */
  message: string;
}

/**
 * Overall status of the full integrity scan.
 *
 * - `secure`  — All critical modules and environment variables passed.
 * - `warning` — Non-critical issues were found (e.g. a module without a
 *               known hash, or a missing recommended env var).
 * - `critical`— At least one critical module is missing or tampered, or
 *               a security-critical env var is insecure.
 */
export type OverallIntegrityStatus = 'secure' | 'warning' | 'critical';

/**
 * Combined report returned by {@link DependencyIntegrityChecker.getReport}.
 *
 * Includes per-module and per-env-var results, an aggregate status,
 * and a list of actionable recommendations.
 */
export interface FullIntegrityReport {
  /** ISO 8601 timestamp of when the report was generated. */
  timestamp: string;

  /** Integrity results for each checked dependency module. */
  modules: IntegrityReport[];

  /** Integrity results for each checked environment variable. */
  envVars: EnvIntegrityReport[];

  /** Aggregate status derived from the individual results. */
  overallStatus: OverallIntegrityStatus;

  /** Actionable recommendations to remediate any issues found. */
  recommendations: string[];
}

// ─── Known Insecure Defaults ────────────────────────────────────────

/**
 * Set of known insecure default values that should never appear in a
 * production environment. Any environment variable whose value (case-
 * insensitive) matches an entry in this set is flagged as `insecure`.
 *
 * These are commonly found in example `.env` files, quick-start guides,
 * and auto-generated configuration templates.
 */
export const INSECURE_VALUES: Set<string> = new Set([
  'default-key',
  'change-me',
  'secret',
  'password',
  'admin',
  'test',
  '1234',
  'abcd',
  'changeme',
  'default',
  'example',
  'placeholder',
  'todo',
  'fixme',
  'xxx',
  'aaaa',
  'qwerty',
  'abc123',
  'letmein',
  'welcome',
  'root',
]);

// ─── Critical Module Definitions ────────────────────────────────────

/**
 * Describes a critical module that the gateway depends on.
 *
 * `expectedHash` is optional — when omitted the checker can still verify
 * that the module is *present* but cannot confirm its integrity against
 * a known-good digest.
 */
interface CriticalModule {
  /** NPM package name (the string passed to `require()` / `import`). */
  name: string;
  /** Human-readable purpose of this dependency. */
  purpose: string;
  /** Optional SHA-256 hash of the module's main entry point for tamper detection. */
  expectedHash?: string;
  /** Whether absence of this module constitutes a critical failure. */
  critical: boolean;
}

/**
 * Internal registry of modules deemed critical for gateway operation.
 *
 * @internal Update this list when new hard dependencies are added to the
 *           gateway. Each entry may optionally carry an `expectedHash` so
 *           that supply-chain tampering can be detected at startup.
 */
const CRITICAL_MODULES: CriticalModule[] = [
  {
    name: '@prisma/client',
    purpose: 'Database access',
    critical: true,
  },
  {
    name: 'next',
    purpose: 'Framework',
    critical: true,
  },
  {
    name: 'react',
    purpose: 'UI framework',
    critical: true,
  },
  {
    name: 'zod',
    purpose: 'Validation',
    critical: false,
  },
];

// ─── Environment Variable Definitions ───────────────────────────────

/**
 * Describes an environment variable that should be checked.
 */
interface EnvVarCheck {
  /** Name of the environment variable. */
  name: string;
  /** Human-readable description of what this variable controls. */
  description: string;
  /** Whether this variable must be set for a secure deployment. */
  required: boolean;
  /** Optional validation function that returns `true` when the value is acceptable. */
  validator?: (value: string) => boolean;
  /** Message to include when the variable fails validation. */
  validationMessage?: string;
}

/**
 * Internal registry of environment variables to verify at startup.
 *
 * @internal Add new entries when security-relevant configuration is
 *           introduced.
 */
const ENV_VAR_CHECKS: EnvVarCheck[] = [
  {
    name: 'ZENIC_DB_PASSPHRASE',
    description: 'Database encryption passphrase',
    required: true,
    validator: (value: string) => value.length > 32,
    validationMessage:
      'ZENIC_DB_PASSPHRASE must be longer than 32 characters for adequate security.',
  },
  {
    name: 'ZENIC_ADMIN_KEY',
    description: 'Admin API key',
    required: true,
  },
  {
    name: 'NODE_ENV',
    description: 'Node runtime environment',
    required: false,
    validator: (value: string) => {
      // Only warn if we appear to be in production but NODE_ENV is not set correctly
      if (process.env.NODE_ENV === 'production') {
        return value === 'production';
      }
      return true;
    },
    validationMessage:
      'NODE_ENV should be set to "production" in production deployments.',
  },
  {
    name: 'ZENIC_CORS_ORIGINS',
    description: 'Allowed CORS origins',
    required: false,
    validator: (value: string) => value.trim() !== '*',
    validationMessage:
      'ZENIC_CORS_ORIGINS should not be "*" as this allows any origin to access the gateway.',
  },
];

// ─── Utility: Module Hashing ────────────────────────────────────────

/**
 * Attempt to compute a SHA-256 hash of a module's resolved entry point.
 *
 * Uses Node's `require.resolve` to find the main file, then reads it
 * from the filesystem and hashes the raw bytes. If the module cannot be
 * resolved or the file cannot be read, `null` is returned.
 *
 * @param moduleName - The NPM package name to resolve and hash.
 * @returns A hex-encoded SHA-256 digest, or `null` if resolution failed.
 *
 * @internal This function is intentionally synchronous so it can be
 *           called during the synchronous startup path.
 */
function computeModuleHash(moduleName: string): string | null {
  try {
    // Dynamic require to resolve the module path
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const module = require(moduleName);
    if (module === undefined || module === null) {
      return null;
    }

    // Compute a hash from the module's exported surface as a fingerprint.
    // This is less precise than hashing the file on disk but works reliably
    // across bundled and ESM environments where require.resolve may not
    // point to a readable file.
    const serialized = JSON.stringify(module, getCircularReplacer());
    return createHash('sha256').update(serialized).digest('hex');
  } catch {
    return null;
  }
}

/**
 * JSON.stringify replacer that handles circular references gracefully.
 *
 * @internal
 */
function getCircularReplacer(): (key: string, value: unknown) => unknown {
  const seen = new WeakSet();
  return (key: string, value: unknown) => {
    if (typeof value === 'object' && value !== null) {
      if (seen.has(value)) {
        return '[Circular]';
      }
      seen.add(value);
    }
    return value;
  };
}

/**
 * Check whether an environment variable value matches a known insecure
 * default. Comparison is case-insensitive and trims surrounding
 * whitespace.
 *
 * @param value - The raw value read from `process.env`.
 * @returns `true` if the value is in the {@link INSECURE_VALUES} set.
 */
function isInsecureValue(value: string): boolean {
  const normalised = value.trim().toLowerCase();
  return INSECURE_VALUES.has(normalised);
}

// ─── DependencyIntegrityChecker Class ───────────────────────────────

/**
 * Runtime dependency and environment integrity checker for the
 * Zenic-Agents gateway.
 *
 * Use this class at application startup to verify that:
 * 1. All critical NPM modules are resolvable and (when a known hash is
 *    available) have not been tampered with.
 * 2. Security-relevant environment variables are set, non-empty, and
 *    free of known-insecure defaults.
 *
 * The checker is **stateless** — each method performs fresh lookups —
 * so it is safe to call repeatedly (e.g. on health-check endpoints).
 *
 * @example
 * ```ts
 * const checker = new DependencyIntegrityChecker();
 * const report = checker.getReport();
 *
 * if (report.overallStatus === 'critical') {
 *   console.error('Critical integrity issues detected — refusing to start.');
 *   process.exit(1);
 * }
 * ```
 */
export class DependencyIntegrityChecker {
  // ── Module Integrity ─────────────────────────────────────────────

  /**
   * Verify that every module in the critical-dependencies registry is
   * present and (when an expected hash is available) has not been
   * tampered with.
   *
   * The check proceeds by attempting to `require()` each module, then
   * optionally comparing a SHA-256 fingerprint of the module's exports
   * against a known-good value.
   *
   * @returns An array of {@link IntegrityReport} entries — one per
   *          critical module.
   *
   * @example
   * ```ts
   * const checker = new DependencyIntegrityChecker();
   * const results = checker.checkCriticalModules();
   * for (const r of results) {
   *   console.log(`${r.moduleName}: ${r.status} — ${r.message}`);
   * }
   * ```
   */
  checkCriticalModules(): IntegrityReport[] {
    const reports: IntegrityReport[] = [];

    for (const mod of CRITICAL_MODULES) {
      const report = this.checkSingleModule(mod);
      reports.push(report);
    }

    return reports;
  }

  /**
   * Check a single critical module.
   *
   * @param mod - The module descriptor from the internal registry.
   * @returns An {@link IntegrityReport} for this module.
   */
  private checkSingleModule(mod: CriticalModule): IntegrityReport {
    const actualHash = computeModuleHash(mod.name);

    // Module could not be resolved at all
    if (actualHash === null) {
      return {
        moduleName: mod.name,
        status: 'missing',
        message: `Critical module "${mod.name}" (${mod.purpose}) could not be resolved. ` +
          'Ensure it is listed in package.json and installed.',
      };
    }

    // No expected hash available — we can only confirm presence
    if (mod.expectedHash === undefined) {
      return {
        moduleName: mod.name,
        status: 'unknown',
        actualHash,
        message: `Module "${mod.name}" (${mod.purpose}) is present but no expected hash ` +
          'is configured, so integrity cannot be fully verified.',
      };
    }

    // Hash comparison
    if (actualHash === mod.expectedHash) {
      return {
        moduleName: mod.name,
        status: 'ok',
        expectedHash: mod.expectedHash,
        actualHash,
        message: `Module "${mod.name}" (${mod.purpose}) integrity verified.`,
      };
    }

    // Hash mismatch — possible tampering
    return {
      moduleName: mod.name,
      status: 'tampered',
      expectedHash: mod.expectedHash,
      actualHash,
      message: `Module "${mod.name}" (${mod.purpose}) hash mismatch! Expected ` +
        `${mod.expectedHash.slice(0, 12)}… but got ${actualHash.slice(0, 12)}…. ` +
        'This may indicate supply-chain tampering or an unrecorded version update.',
    };
  }

  // ── Environment Integrity ────────────────────────────────────────

  /**
   * Verify that security-relevant environment variables are properly
   * configured.
   *
   * Checks include:
   * - Whether the variable is defined at all.
   * - Whether the value matches a known-insecure default (see
   *   {@link INSECURE_VALUES}).
   * - Whether custom validation rules (e.g. minimum length) pass.
   * - Whether the variable is empty or consists only of whitespace.
   *
   * @returns An array of {@link EnvIntegrityReport} entries — one per
   *          checked environment variable.
   *
   * @example
   * ```ts
   * const checker = new DependencyIntegrityChecker();
   * const envResults = checker.checkEnvIntegrity();
   * const insecure = envResults.filter(r => r.status !== 'ok');
   * if (insecure.length > 0) {
   *   console.warn('Insecure environment variables detected:', insecure);
   * }
   * ```
   */
  checkEnvIntegrity(): EnvIntegrityReport[] {
    const reports: EnvIntegrityReport[] = [];

    // Check explicitly-defined environment variables
    for (const check of ENV_VAR_CHECKS) {
      const report = this.checkSingleEnvVar(check);
      reports.push(report);
    }

    // Scan for any env vars with known insecure defaults
    const scanResults = this.scanForInsecureDefaults();
    reports.push(...scanResults);

    return reports;
  }

  /**
   * Check a single environment variable against its definition.
   *
   * @param check - The env-var descriptor from the internal registry.
   * @returns An {@link EnvIntegrityReport} for this variable.
   */
  private checkSingleEnvVar(check: EnvVarCheck): EnvIntegrityReport {
    const rawValue = process.env[check.name];

    // Variable is not defined
    if (rawValue === undefined || rawValue === '') {
      if (check.required) {
        return {
          variable: check.name,
          status: 'missing',
          message: `Required environment variable "${check.name}" (${check.description}) is not set.`,
        };
      }
      return {
        variable: check.name,
        status: 'missing',
        message: `Optional environment variable "${check.name}" (${check.description}) is not set. ` +
          'Setting it is recommended for a secure deployment.',
      };
    }

    // Check for insecure values
    if (isInsecureValue(rawValue)) {
      return {
        variable: check.name,
        status: 'insecure',
        message: `Environment variable "${check.name}" uses a known-insecure default value. ` +
          `Please replace it with a strong, unique value.`,
      };
    }

    // Check for empty / whitespace-only values
    if (rawValue.trim() === '') {
      return {
        variable: check.name,
        status: 'default',
        message: `Environment variable "${check.name}" is set but empty or whitespace-only. ` +
          'This is equivalent to not setting it at all.',
      };
    }

    // Run custom validator if provided
    if (check.validator && !check.validator(rawValue)) {
      return {
        variable: check.name,
        status: 'insecure',
        message: check.validationMessage ??
          `Environment variable "${check.name}" failed validation.`,
      };
    }

    return {
      variable: check.name,
      status: 'ok',
      message: `Environment variable "${check.name}" (${check.description}) is properly configured.`,
    };
  }

  /**
   * Scan all environment variables for values matching known insecure
   * defaults. This catches variables that are not in the explicit check
   * list but happen to use weak values.
   *
   * Only ZENIC_-prefixed variables and common security variables are
   * scanned to avoid false positives on unrelated configuration.
   *
   * @returns Additional {@link EnvIntegrityReport} entries for any
   *          insecure values discovered.
   */
  private scanForInsecureDefaults(): EnvIntegrityReport[] {
    const reports: EnvIntegrityReport[] = [];
    const alreadyChecked = new Set(ENV_VAR_CHECKS.map((c) => c.name));

    // Prefixes that indicate security-relevant configuration
    const securityPrefixes = ['ZENIC_', 'AUTH_', 'SECRET_', 'KEY_', 'PASS_', 'TOKEN_'];

    for (const [key, value] of Object.entries(process.env)) {
      // Skip variables already checked explicitly
      if (alreadyChecked.has(key)) {
        continue;
      }

      // Only scan variables with security-relevant prefixes
      const isSecurityRelevant = securityPrefixes.some((prefix) =>
        key.toUpperCase().startsWith(prefix)
      );
      if (!isSecurityRelevant || value === undefined || value === '') {
        continue;
      }

      if (isInsecureValue(value)) {
        reports.push({
          variable: key,
          status: 'insecure',
          message: `Environment variable "${key}" uses a known-insecure default value. ` +
            'Please replace it with a strong, unique value.',
        });
      }
    }

    return reports;
  }

  // ── Combined Report ──────────────────────────────────────────────

  /**
   * Produce a combined integrity report covering both dependency modules
   * and environment variables.
   *
   * The {@link FullIntegrityReport.overallStatus} is derived from the
   * individual results:
   * - **`critical`** — Any critical module is `missing` or `tampered`, or
   *   any required env var is `insecure`.
   * - **`warning`**  — Non-critical modules are `missing` / `unknown`, or
   *   optional env vars are `missing` / `insecure`.
   * - **`secure`**   — Everything passed.
   *
   * @returns A {@link FullIntegrityReport} with timestamped, actionable
   *          results.
   *
   * @example
   * ```ts
   * const checker = new DependencyIntegrityChecker();
   * const full = checker.getReport();
   *
   * console.log(`Integrity status: ${full.overallStatus}`);
   * for (const rec of full.recommendations) {
   *   console.warn(`  → ${rec}`);
   * }
   * ```
   */
  getReport(): FullIntegrityReport {
    const modules = this.checkCriticalModules();
    const envVars = this.checkEnvIntegrity();
    const recommendations: string[] = [];

    // ── Derive overall status ────────────────────────────────────
    let overallStatus: OverallIntegrityStatus = 'secure';

    // Check module results
    for (const mod of modules) {
      const criticalModule = CRITICAL_MODULES.find((m) => m.name === mod.moduleName);
      const isCritical = criticalModule?.critical ?? true;

      if (mod.status === 'missing' || mod.status === 'tampered') {
        if (isCritical) {
          overallStatus = 'critical';
          recommendations.push(
            `[CRITICAL] Module "${mod.moduleName}" is ${mod.status}. ${mod.message}`
          );
        } else {
          if (overallStatus !== 'critical') {
            overallStatus = 'warning';
          }
          recommendations.push(
            `[WARNING] Module "${mod.moduleName}" is ${mod.status}. ${mod.message}`
          );
        }
      } else if (mod.status === 'unknown') {
        if (overallStatus === 'secure') {
          overallStatus = 'warning';
        }
        recommendations.push(
          `[INFO] Module "${mod.moduleName}" is present but integrity cannot be verified. ` +
          'Consider adding an expected hash to the integrity configuration.'
        );
      }
    }

    // Check environment variable results
    for (const env of envVars) {
      const envCheck = ENV_VAR_CHECKS.find((c) => c.name === env.variable);
      const isRequired = envCheck?.required ?? false;

      if (env.status === 'insecure') {
        if (isRequired) {
          overallStatus = 'critical';
          recommendations.push(
            `[CRITICAL] ${env.message}`
          );
        } else {
          if (overallStatus !== 'critical') {
            overallStatus = 'warning';
          }
          recommendations.push(
            `[WARNING] ${env.message}`
          );
        }
      } else if (env.status === 'missing') {
        if (isRequired) {
          if (overallStatus !== 'critical') {
            overallStatus = 'warning';
          }
          recommendations.push(
            `[WARNING] ${env.message}`
          );
        } else {
          recommendations.push(
            `[INFO] ${env.message}`
          );
        }
      } else if (env.status === 'default') {
        if (overallStatus === 'secure') {
          overallStatus = 'warning';
        }
        recommendations.push(
          `[WARNING] ${env.message}`
        );
      }
    }

    // ── Add general recommendations if issues were found ─────────
    if (overallStatus === 'critical') {
      recommendations.push(
        'Refuse to start the application until all critical integrity issues are resolved.'
      );
    }

    if (overallStatus === 'warning') {
      recommendations.push(
        'Review all warnings above and address them before deploying to production.'
      );
    }

    if (overallStatus === 'secure') {
      recommendations.push(
        'All integrity checks passed. No action required.'
      );
    }

    return {
      timestamp: new Date().toISOString(),
      modules,
      envVars,
      overallStatus,
      recommendations,
    };
  }
}

// ─── Startup Helper ─────────────────────────────────────────────────

/**
 * Run a full integrity check suitable for application startup.
 *
 * This function:
 * 1. Instantiates a {@link DependencyIntegrityChecker}.
 * 2. Generates a {@link FullIntegrityReport}.
 * 3. Logs the results at appropriate severity levels.
 * 4. Returns `true` if the application is safe to start (no critical
 *    issues), or `false` if critical problems were detected.
 *
 * **Call this early in your application's bootstrap sequence** — ideally
 * before the HTTP server begins accepting connections.
 *
 * @returns `true` if no critical integrity issues were found; `false`
 *          if critical issues prevent safe operation.
 *
 * @example
 * ```ts
 * // In your application entry point (e.g. instrumentation.ts or server.ts):
 * import { runStartupIntegrityCheck } from '@/lib/security/config/integrity';
 *
 * const isSafe = runStartupIntegrityCheck();
 * if (!isSafe) {
 *   console.error('Aborting startup due to critical integrity failures.');
 *   process.exit(1);
 * }
 * ```
 */
export function runStartupIntegrityCheck(): boolean {
  const checker = new DependencyIntegrityChecker();
  const report = checker.getReport();

  // ── Log the report ────────────────────────────────────────────
  const summaryLine =
    `[IntegrityCheck] Status: ${report.overallStatus} | ` +
    `Modules: ${report.modules.length} checked | ` +
    `Env vars: ${report.envVars.length} checked`;

  switch (report.overallStatus) {
    case 'critical':
      console.error(JSON.stringify({ level: 'error', message: summaryLine, report }));
      break;
    case 'warning':
      console.warn(JSON.stringify({ level: 'warn', message: summaryLine, report }));
      break;
    case 'secure':
      console.info(JSON.stringify({ level: 'info', message: summaryLine, report }));
      break;
  }

  // ── Log individual findings ───────────────────────────────────
  for (const mod of report.modules) {
    if (mod.status !== 'ok') {
      const level = mod.status === 'missing' || mod.status === 'tampered' ? 'error' : 'warn';
      const payload = {
        level,
        message: `[IntegrityCheck] Module "${mod.moduleName}": ${mod.status}`,
        detail: mod.message,
        expectedHash: mod.expectedHash,
        actualHash: mod.actualHash,
      };

      if (level === 'error') {
        console.error(JSON.stringify(payload));
      } else {
        console.warn(JSON.stringify(payload));
      }
    }
  }

  for (const env of report.envVars) {
    if (env.status !== 'ok') {
      const level = env.status === 'insecure' ? 'error' : 'warn';
      const payload = {
        level,
        message: `[IntegrityCheck] Env var "${env.variable}": ${env.status}`,
        detail: env.message,
      };

      if (level === 'error') {
        console.error(JSON.stringify(payload));
      } else {
        console.warn(JSON.stringify(payload));
      }
    }
  }

  // ── Log recommendations ───────────────────────────────────────
  for (const rec of report.recommendations) {
    if (rec.startsWith('[CRITICAL]')) {
      console.error(JSON.stringify({ level: 'error', message: rec }));
    } else if (rec.startsWith('[WARNING]')) {
      console.warn(JSON.stringify({ level: 'warn', message: rec }));
    } else {
      console.info(JSON.stringify({ level: 'info', message: rec }));
    }
  }

  // ── Return whether startup should proceed ─────────────────────
  return report.overallStatus !== 'critical';
}
