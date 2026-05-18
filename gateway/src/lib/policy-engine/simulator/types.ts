// ─── Zenic-Agents v3 — Policy Simulator (What-If Analysis) ──────────
// Phase 4: Declarative Versioned Policy Engine — Simulation Module
//
// Design Patterns:
//   - Command: Each SimulationChange is a command that modifies the policy set
//   - Memento: Before/after snapshots for verdict comparison
//   - Strategy: Impact scoring with configurable category weights
//
// Evaluation Flow:
//   1. Load current active policies from DB
//   2. Deep-clone → simulated policy set
//   3. Apply each SimulationChange as a command
//   4. For each test request:
//      a. Evaluate against CURRENT set → "before" result
//      b. Evaluate against SIMULATED set → "after" result
//      c. If different → record as VerdictChange
//   5. Run conflict detection on both sets
//   6. Calculate impact score from verdict changes
//   7. Assess compliance impact
//   8. Persist and return SimulationResult

import { db } from "@/lib/db";
import { PolicyEffectV2 } from "./types";
import type {
  PolicyDocument,
  PolicyStatement,
  PolicyEvaluationRequest,
  PolicyEvaluationResult,
} from "./types";
import {
  SimulationChangeType,
  VerdictChangeCategory,
  SimulationRiskLevel,
  ConflictSeverity,
  ConflictType,
  ConflictResolutionStrategy,
} from "./types";
import type {
  SimulationRequest,
  SimulationChange,
  SimulationResult,
  VerdictChange,
  SimulationRisk,
  ComplianceImpact,
  SimulationTrace,
  PolicyConflict,
  ConflictStatementRef,
} from "./types";
import { PolicyEvaluator, getPolicyEvaluator } from "./evaluator";

// ─── Local Types ─────────────────────────────────────────────────────

/** Options for listing simulations */
export interface ListSimulationsOptions {
  /** Filter by requester */
  requestedBy?: string;
  /** Filter by risk level */
  riskLevel?: SimulationRiskLevel;
  /** Maximum results to return */
  limit?: number;
  /** Pagination offset */
  offset?: number;
}

// ─── Deep Clone Helper ───────────────────────────────────────────────

/**
 * Deep clone a value using JSON serialization.
 * Safe for PolicyDocument trees which are plain JSON-compatible objects.
 */
function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

// ─── Pattern Overlap Helper ──────────────────────────────────────────

/**
 * Check if two resource/action patterns could match the same concrete value.
 * Supports wildcard suffixes ("financial/*") and full wildcards ("*").
 */
function patternsOverlap(patternA: string, patternB: string): boolean {
  if (patternA === "*" || patternB === "*") return true;
  if (patternA === patternB) return true;

  // Wildcard suffix: "financial/*" could match anything under "financial/"
  if (patternA.endsWith("/*") && patternB.endsWith("/*")) {
    const prefixA = patternA.slice(0, -2);
    const prefixB = patternB.slice(0, -2);
    return prefixA === prefixB || prefixA.startsWith(`${prefixB}/`) || prefixB.startsWith(`${prefixA}/`);
  }

  // One wildcard, one concrete
  if (patternA.endsWith("/*")) {
    const prefix = patternA.slice(0, -2);
    return patternB === prefix || patternB.startsWith(`${prefix}/`);
  }
  if (patternB.endsWith("/*")) {
    const prefix = patternB.slice(0, -2);
    return patternA === prefix || patternA.startsWith(`${prefix}/`);
  }

  return false;
}

// ─── ID Generation ───────────────────────────────────────────────────

/** Generate a unique simulation ID */
function generateSimulationId(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `sim_${ts}_${rand}`;
}

// ─── Load Active Policies ────────────────────────────────────────────

/**
 * Load all active policies from the database and convert to PolicyDocument[].
 * Mirrors PolicyEvaluator.loadActivePolicies logic.
 */
async function loadActivePoliciesFromDb(): Promise<PolicyDocument[]> {
  const policies = await db.declPolicy.findMany({
    where: { isActive: true },
    orderBy: { updatedAt: "desc" },
  });

  return policies.map((p) => ({
    apiVersion: p.apiVersion,
    kind: "PolicyDocument" as const,
    metadata: {
      id: p.policyId,
      name: p.name,
      version: p.version,
      description: p.description,
      compliance: JSON.parse(p.compliance) as import("./types").ComplianceMapping[],
      labels: JSON.parse(p.labels) as Record<string, string>,
      author: p.author ?? undefined,
      createdAt: p.createdAt.toISOString(),
      updatedAt: p.updatedAt.toISOString(),
    },
    statements: JSON.parse(p.statements) as PolicyStatement[],
    tests: JSON.parse(p.tests) as import("./types").PolicyTestCase[],
  }));
}

// ─── Evaluation Against Policy Set ───────────────────────────────────

/**
 * Evaluate a request against an array of policy documents.
 * Collects all matching statements across all documents,
 * sorts by priority (deny wins on tie), and returns the top match.
