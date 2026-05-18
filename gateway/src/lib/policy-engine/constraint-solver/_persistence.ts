// ─── Verification Persistence ──────────────────────────────────────────
// Functions for persisting and loading verification results from the database.

import { db } from "@/lib/db";
import type { VerificationResult, VerificationStatus, SolverType } from "../types/constraints";
import type { Contradiction, UnreachableRule, CoverageReport } from "../types/constraints";
import { generateVerificationId } from "./helpers";

/** Options for listing verification results */
export interface ListVerificationsOptions {
  /** Filter by status */
  status?: VerificationStatus;
  /** Filter by consistent flag */
  consistent?: boolean;
  /** Maximum number of results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

/**
 * Persist a verification result to the PolicyVerification table.
 */
export async function persistVerification(policyIds: string[], result: VerificationResult): Promise<void> {
  const verificationId = generateVerificationId();

  await db.policyVerification.create({
    data: {
      verificationId,
      policyIds: JSON.stringify(policyIds),
      consistent: result.contradictions.filter(
        (c) => c.type === "effect_conflict" || c.type === "unsatisfiable_condition",
      ).length === 0,
      complete: result.complete,
      hasUnreachableRules: result.hasUnreachableRules,
      status: result.status,
      contradictions: JSON.stringify(result.contradictions),
      unreachableRules: JSON.stringify(result.unreachableRules),
      coverage: JSON.stringify(result.coverage),
      solverType: result.solverType,
      duration: result.duration,
      summary: result.summary,
    },
  });
}

/**
 * Load a verification result by its ID.
 *
 * @param verificationId - The verification ID to look up.
 * @returns The VerificationResult, or null if not found.
 */
export async function getVerification(verificationId: string): Promise<VerificationResult | null> {
  try {
    const record = await db.policyVerification.findUnique({
      where: { verificationId },
    });

    if (!record) return null;

    const contradictions = JSON.parse(record.contradictions) as Contradiction[];
    const coverage = JSON.parse(record.coverage) as CoverageReport;
    const unreachableRules = JSON.parse(record.unreachableRules) as UnreachableRule[];

    return {
      consistent: record.consistent,
      complete: record.complete,
      hasUnreachableRules: record.hasUnreachableRules,
      status: record.status as VerificationStatus,
      contradictions,
      unreachableRules,
      coverage,
      duration: record.duration,
      solverType: record.solverType as SolverType,
      summary: record.summary,
    };
  } catch (error) {
    console.error(`[ConstraintSolver] Error loading verification ${verificationId}:`, error);
    return null;
  }
}

/**
 * List verification results with optional filtering and pagination.
 *
 * @param options - Filter and pagination options.
 * @returns Array of VerificationResult objects.
 */
export async function listVerifications(options?: ListVerificationsOptions): Promise<VerificationResult[]> {
  try {
    const where: Record<string, unknown> = {};

    if (options?.status) {
      where.status = options.status;
    }
    if (options?.consistent !== undefined) {
      where.consistent = options.consistent;
    }

    const records = await db.policyVerification.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 50,
      skip: options?.offset ?? 0,
    });

    return records.map((record) => {
      const contradictions = JSON.parse(record.contradictions) as Contradiction[];
      const coverage = JSON.parse(record.coverage) as CoverageReport;
      const unreachableRules = JSON.parse(record.unreachableRules) as UnreachableRule[];

      return {
        consistent: record.consistent,
        complete: record.complete,
        hasUnreachableRules: record.hasUnreachableRules,
        status: record.status as VerificationStatus,
        contradictions,
        unreachableRules,
        coverage,
        duration: record.duration,
        solverType: record.solverType as SolverType,
        summary: record.summary,
      };
    });
  } catch (error) {
    console.error("[ConstraintSolver] Error listing verifications:", error);
    return [];
  }
}
