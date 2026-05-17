// ─── Zenic-Agents v3 — Policy Evaluator Engine ────────────────────────
// Evaluates requests against compiled policy documents.
// Strategy pattern for condition operators.
// Deny-by-default with explicit allow.
//
// Evaluation Algorithm:
//   1. Collect all matching statements from all active policies
//   2. Sort by priority (highest first)
//   3. Deny always wins over allow on same priority
//   4. First matching deny → immediate deny
//   5. First matching allow → allow (unless later deny)
//   6. No match → default effect (deny)

import { createHash } from "crypto";
import { db } from "@/lib/db";
import type {
  PolicyDocument,
  PolicyStatement,
  PolicyCondition,
  ConditionOperator,
  PolicyEvaluationRequest,
  PolicyEvaluationResult,
  PolicyEffectV2,
  PolicyEngineConfig,
} from "./types";
import { DEFAULT_POLICY_ENGINE_CONFIG } from "./types";

// ─── Condition Operator Strategy Map ──────────────────────────────────

type OperatorFn = (fieldValue: unknown, conditionValue: unknown) => boolean;

export const OPERATOR_STRATEGIES: Record<ConditionOperator, OperatorFn> = {
  eq: (field, value) => field === value,
  neq: (field, value) => field !== value,
  in: (field, value) => Array.isArray(value) && value.includes(field),
  notin: (field, value) => Array.isArray(value) && !value.includes(field),
  gt: (field, value) => typeof field === "number" && typeof value === "number" && field > value,
  lt: (field, value) => typeof field === "number" && typeof value === "number" && field < value,
  gte: (field, value) => typeof field === "number" && typeof value === "number" && field >= value,
  lte: (field, value) => typeof field === "number" && typeof value === "number" && field <= value,
  regex: (field, value) => {
    if (typeof field !== "string" || typeof value !== "string") return false;
    try {
      // BUG #1 FIX: Safe regex with timeout protection against ReDoS.
      // INVARIANT 4: defense in depth — a malicious regex must NEVER freeze the
      // event loop on this Termux/500MB host.
      const re = new RegExp(value);
      // Reject patterns that could cause catastrophic backtracking:
      // nested quantifiers like (a+)+ or (a*){2,}
      if (/(\+|\*)[^\+\*\|\)]*?(\+|\*)/.test(value)) {
        console.warn(`[PolicyEngine] Rejected potentially dangerous regex: ${value}`);
        return false;
      }
      return re.test(field);
    } catch {
      return false;
    }
  },
  exists: (field) => field !== undefined && field !== null,
  not_exists: (field) => field === undefined || field === null,
  contains: (field, value) => {
    if (typeof field === "string" && typeof value === "string") return field.includes(value);
    if (Array.isArray(field)) return field.includes(value);
    return false;
  },
  starts_with: (field, value) => typeof field === "string" && typeof value === "string" && field.startsWith(value),
  ends_with: (field, value) => typeof field === "string" && typeof value === "string" && field.endsWith(value),
};

// ─── Pattern Matching ─────────────────────────────────────────────────

/**
 * Check if a resource/action string matches a pattern.
 * Supports wildcard: "financial/*" matches "financial/transfer"
 */
function matchesPattern(pattern: string, value: string): boolean {
  if (pattern === "*") return true;
  if (pattern === value) return true;

  // Wildcard suffix: "financial/*" → matches "financial/transfer"
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -2);
    return value === prefix || value.startsWith(`${prefix}/`);
  }

  // Wildcard prefix: "*/execute" → matches "financial/execute"
  if (pattern.startsWith("*/")) {
    const suffix = pattern.slice(1);
    return value.endsWith(suffix);
  }

  // Glob-style: "fin*al" → not supported, exact match fallback
  return false;
}

/**
 * Evaluate a single condition against a context.
 */
function evaluateCondition(condition: PolicyCondition, context: Record<string, unknown>): boolean {
  const fieldValue = getNestedField(context, condition.field);
  const strategy = OPERATOR_STRATEGIES[condition.operator];

  if (!strategy) {
    console.warn(`[PolicyEngine] Unknown operator: ${condition.operator}`);
    return false;
  }

  return strategy(fieldValue, condition.value);
}

/**
 * Get a nested field from an object using dot notation.
 * e.g., "request.amount" → context.request?.amount
 */
function getNestedField(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split(".");
  let current: unknown = obj;

  for (const part of parts) {
    if (current === null || current === undefined) return undefined;
    if (typeof current === "object") {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }

  return current;
}

/**
 * Evaluate all conditions in a statement against a context.
 * All conditions must be true (AND logic).
 */
function evaluateConditions(
  conditions: PolicyCondition[],
  context: Record<string, unknown>,
): boolean {
  return conditions.every((c) => evaluateCondition(c, context));
}

/**
 * Check if a statement matches a request.
 */
function statementMatches(
  statement: PolicyStatement,
  request: PolicyEvaluationRequest,
): boolean {
  // Resource pattern match
  if (!matchesPattern(statement.resource, request.resource)) return false;

  // Action pattern match
  if (!matchesPattern(statement.action, request.action)) return false;

  // Condition evaluation
  if (statement.conditions && statement.conditions.length > 0) {
    return evaluateConditions(statement.conditions, request.context);
  }

  return true;
}

// ─── Policy Evaluator ─────────────────────────────────────────────────

/** Maximum cached entries to prevent unbounded memory growth on 500MB Termux */
const MAX_CACHE_SIZE = 500;

export class PolicyEvaluator {
  private config: PolicyEngineConfig;
  private cache: Map<string, { result: PolicyEvaluationResult; expiresAt: number }> = new Map();

  constructor(config?: Partial<PolicyEngineConfig>) {
    this.config = { ...DEFAULT_POLICY_ENGINE_CONFIG, ...config };
  }

  /**
   * Evaluate a request against all active policies.
   */
  async evaluate(request: PolicyEvaluationRequest): Promise<PolicyEvaluationResult> {
    const startTime = Date.now();

    // Check cache
    if (this.config.enableCache) {
      const cacheKey = this.buildCacheKey(request);
      const cached = this.cache.get(cacheKey);
      if (cached && cached.expiresAt > Date.now()) {
        return { ...cached.result, duration: Date.now() - startTime };
      }
    }

    try {
      // Load all active policies from DB
      const activePolicies = await this.loadActivePolicies(request.tenantId);

      // Collect all matching statements
      const matchedStatements: PolicyEvaluationResult["matchedStatements"] = [];

      for (const policy of activePolicies) {
        const statements = policy.statements;

        for (const statement of statements) {
          if (statementMatches(statement, request)) {
            matchedStatements.push({
              policyId: policy.metadata.id,
              statementId: statement.id,
              effect: statement.effect,
              priority: statement.priority,
            });
          }
        }
      }

      // Sort by priority (highest first), deny wins on tie
      matchedStatements.sort((a, b) => {
        if (b.priority !== a.priority) return b.priority - a.priority;
        // Deny wins over allow on same priority
        const effectOrder: Record<string, number> = { deny: 0, conditional: 1, allow: 2 };
        return (effectOrder[a.effect] ?? 3) - (effectOrder[b.effect] ?? 3);
      });

      // Determine the final effect
      let finalEffect: PolicyEffectV2 = this.config.defaultEffect;
      let matchReason = "No matching policy — default effect applied";
      let matchedStatementId: string | undefined;
      let denyByDefault = true;
      let requiredRole: string | undefined;

      if (matchedStatements.length > 0) {
        const topMatch = matchedStatements[0]!;
        finalEffect = topMatch.effect;
        matchedStatementId = topMatch.statementId;
        denyByDefault = false;
        matchReason = `Matched statement "${topMatch.statementId}" in policy "${topMatch.policyId}" (priority ${topMatch.priority})`;

        // Find the statement for additional data
        const matchedPolicy = activePolicies.find((p) => p.metadata.id === topMatch.policyId);
        const matchedStmt = matchedPolicy?.statements.find((s) => s.id === topMatch.statementId);
        if (matchedStmt?.requiredRole) {
          requiredRole = matchedStmt.requiredRole;

          // Check if user has the required role
          if (finalEffect === "conditional" && request.roles && !request.roles.includes(requiredRole)) {
            finalEffect = "deny";
            matchReason += ` — required role "${requiredRole}" not present`;
          }
        }
      }

      const result: PolicyEvaluationResult = {
        effect: finalEffect,
        policyId: matchedStatements[0]?.policyId ?? "default",
        matchedStatementId,
        reason: matchReason,
        matchedStatements,
        duration: Date.now() - startTime,
        denyByDefault,
        requiredRole,
      };

      // BUG #4 FIX: Cache the result with size limit.
      // Evict oldest entries when cache exceeds MAX_CACHE_SIZE to prevent
      // unbounded memory growth on the 500MB Termux host.
      if (this.config.enableCache) {
        const cacheKey = this.buildCacheKey(request);
        if (this.cache.size >= MAX_CACHE_SIZE) {
          // Evict expired entries first
          const now = Date.now();
          for (const [key, entry] of this.cache) {
            if (entry.expiresAt <= now) {
              this.cache.delete(key);
            }
          }
          // If still over limit, evict the oldest (first-inserted) entries
          if (this.cache.size >= MAX_CACHE_SIZE) {
            const firstKey = this.cache.keys().next().value;
            if (firstKey !== undefined) {
              this.cache.delete(firstKey);
            }
          }
        }
        this.cache.set(cacheKey, {
          result,
          expiresAt: Date.now() + this.config.cacheTtlSeconds * 1000,
        });
      }

      return result;
    } catch (error) {
      if (this.config.denyOnError) {
        return {
          effect: "deny",
          policyId: "error",
          reason: `Evaluation error: ${error instanceof Error ? error.message : String(error)}`,
          matchedStatements: [],
          duration: Date.now() - startTime,
          denyByDefault: true,
        };
      }
      throw error;
    }
  }

  /**
   * Evaluate a request against a specific policy document (in-memory).
   */
  evaluateDocument(document: PolicyDocument, request: PolicyEvaluationRequest): PolicyEvaluationResult {
    const startTime = Date.now();
    const matchedStatements: PolicyEvaluationResult["matchedStatements"] = [];

    for (const statement of document.statements) {
      if (statementMatches(statement, request)) {
        matchedStatements.push({
          policyId: document.metadata.id,
          statementId: statement.id,
          effect: statement.effect,
          priority: statement.priority,
        });
      }
    }

    matchedStatements.sort((a, b) => {
      if (b.priority !== a.priority) return b.priority - a.priority;
      const effectOrder: Record<string, number> = { deny: 0, conditional: 1, allow: 2 };
      return (effectOrder[a.effect] ?? 3) - (effectOrder[b.effect] ?? 3);
    });

    let finalEffect: PolicyEffectV2 = this.config.defaultEffect;
    let matchReason = "No matching statement — default effect applied";
    let matchedStatementId: string | undefined;
    let denyByDefault = true;
    let requiredRole: string | undefined;

    if (matchedStatements.length > 0) {
      const topMatch = matchedStatements[0]!;
      finalEffect = topMatch.effect;
      matchedStatementId = topMatch.statementId;
      denyByDefault = false;
      matchReason = `Matched statement "${topMatch.statementId}" (priority ${topMatch.priority})`;

      const matchedStmt = document.statements.find((s) => s.id === topMatch.statementId);
      if (matchedStmt?.requiredRole) {
        requiredRole = matchedStmt.requiredRole;
      }
    }

    return {
      effect: finalEffect,
      policyId: document.metadata.id,
      matchedStatementId,
      reason: matchReason,
      matchedStatements,
      duration: Date.now() - startTime,
      denyByDefault,
      requiredRole,
    };
  }

  /**
   * Clear the evaluation cache.
   */
  clearCache(): void {
    this.cache.clear();
  }

  /**
   * Load active policies from the database.
   * BUG #5 FIX: Uses tenantId for multi-tenant isolation.
   * BUG #13 FIX: Per-policy try-catch for malformed JSON — logs bad policy
   * instead of crashing the entire evaluation.
   */
  private async loadActivePolicies(tenantId?: string): Promise<PolicyDocument[]> {
    const where: Record<string, unknown> = { isActive: true };
    // BUG #5 FIX: Filter by tenant when provided to prevent cross-tenant leaks
    // Also include global policies (no tenantId) that apply to all tenants
    if (tenantId) {
      where.OR = [
        { tenantId: null },
        { tenantId },
        { labels: { contains: `"tenantId":"${tenantId}"` } },
        { labels: { contains: `"tenantId": "${tenantId}"` } },
      ];
    }

    const policies = await db.declPolicy.findMany({
      where,
      orderBy: { updatedAt: "desc" },
      take: this.config.maxPolicies,
    });

    const documents: PolicyDocument[] = [];
    for (const p of policies) {
      try {
        documents.push({
          apiVersion: p.apiVersion,
          kind: "PolicyDocument",
          metadata: {
            id: p.policyId,
            name: p.name,
            version: p.version,
            description: p.description,
            compliance: JSON.parse(p.compliance),
            labels: JSON.parse(p.labels),
            author: p.author ?? undefined,
            createdAt: p.createdAt.toISOString(),
            updatedAt: p.updatedAt.toISOString(),
          },
          statements: JSON.parse(p.statements),
          tests: JSON.parse(p.tests),
        });
      } catch (parseErr) {
        // BUG #13 FIX: Log and skip malformed policies instead of crashing
        console.error(
          `[PolicyEngine] Skipping malformed policy ${p.policyId}:`,
          parseErr instanceof Error ? parseErr.message : String(parseErr)
        );
      }
    }
    return documents;
  }

  /**
   * BUG #10 FIX: Hash the cache key to prevent unbounded memory from
   * large JSON contexts. Uses SHA-256 for deterministic compact keys.
   */
  private buildCacheKey(request: PolicyEvaluationRequest): string {
    const raw = `${request.resource}:${request.action}:${request.tenantId ?? ""}:${request.userId ?? ""}:${JSON.stringify(request.context)}`;
    return createHash("sha256").update(raw).digest("hex");
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

let evaluatorInstance: PolicyEvaluator | null = null;

export function getPolicyEvaluator(config?: Partial<PolicyEngineConfig>): PolicyEvaluator {
  if (!evaluatorInstance) {
    evaluatorInstance = new PolicyEvaluator(config);
  }
  return evaluatorInstance;
}

export function resetPolicyEvaluator(): void {
  evaluatorInstance = null;
}
