// ─── Zenic-Agents v3 — Policy Test Runner ─────────────────────────────
// Executes test cases defined within policy documents.
// Validates that policy statements produce expected outcomes.
//
// Pattern: Test Runner — orchestrates test execution and reporting

import { db } from "@/lib/db";
import { PolicyEvaluator } from "./evaluator";
import type {
  PolicyDocument,
  PolicyTestCase,
  PolicyTestResult,
  PolicyTestSuiteResult,
  PolicyTestExpectation,
  PolicyEvaluationResult,
} from "./types";

// ─── Test Runner ──────────────────────────────────────────────────────

/**
 * Run all tests for a policy document.
 */
export function runPolicyTests(
  document: PolicyDocument,
  evaluator?: PolicyEvaluator,
): PolicyTestSuiteResult {
  const startTime = Date.now();
  const tests = document.tests ?? [];
  const eval_ = evaluator ?? new PolicyEvaluator();

  const results: PolicyTestResult[] = [];
  let passed = 0;
  let failed = 0;
  let errors = 0;

  for (const testCase of tests) {
    try {
      const result = runSingleTest(testCase, document, eval_);
      results.push(result);

      if (result.passed) {
        passed++;
      } else {
        failed++;
      }
    } catch (err) {
      results.push({
        testName: testCase.name,
        passed: false,
        expected: testCase.expected,
        actual: "denied" as PolicyTestExpectation,
        error: err instanceof Error ? err.message : String(err),
      });
      errors++;
    }
  }

  const duration = Date.now() - startTime;

  return {
    policyId: document.metadata.id,
    version: document.metadata.version,
    total: tests.length,
    passed,
    failed,
    errors,
    results,
    duration,
    suitePassed: failed === 0 && errors === 0,
  };
}

/**
 * Run a single test case against a policy document.
 */
function runSingleTest(
  testCase: PolicyTestCase,
  document: PolicyDocument,
  evaluator: PolicyEvaluator,
): PolicyTestResult {
  const evaluationResult = evaluator.evaluateDocument(document, {
    resource: testCase.resource,
    action: testCase.action,
    context: testCase.context,
  });

  // Map evaluation effect to test expectation
  const actualEffect = evaluationResult.effect;
  const actual: PolicyTestExpectation = actualEffect === "allow"
    ? "allowed"
    : actualEffect === "deny"
      ? "denied"
      : "conditional";

  const passed = actual === testCase.expected;

  // Check expectedStatementId if specified
  let statementIdMatches = true;
  if (testCase.expectedStatementId) {
    statementIdMatches = evaluationResult.matchedStatementId === testCase.expectedStatementId;
  }

  return {
    testName: testCase.name,
    passed: passed && statementIdMatches,
    expected: testCase.expected,
    actual,
    matchedStatementId: evaluationResult.matchedStatementId,
    evaluationDetails: evaluationResult,
  };
}

/**
 * Run tests for a policy stored in the database and persist results.
 */
export async function runAndStoreTests(
  policyId: string,
  triggeredBy: string = "manual",
): Promise<PolicyTestSuiteResult> {
  // Load policy from DB
  const policy = await db.declPolicy.findUnique({ where: { policyId } });
  if (!policy) {
    throw new Error(`Policy "${policyId}" not found`);
  }

  const document: PolicyDocument = {
    apiVersion: policy.apiVersion,
    kind: "PolicyDocument",
    metadata: {
      id: policy.policyId,
      name: policy.name,
      version: policy.version,
      description: policy.description,
      compliance: JSON.parse(policy.compliance),
      labels: JSON.parse(policy.labels),
      author: policy.author ?? undefined,
      createdAt: policy.createdAt.toISOString(),
      updatedAt: policy.updatedAt.toISOString(),
    },
    statements: JSON.parse(policy.statements),
    tests: JSON.parse(policy.tests),
  };

  const result = runPolicyTests(document);

  // Persist test results
  await db.declPolicyTestResult.create({
    data: {
      policyId,
      version: policy.version,
      totalTests: result.total,
      passed: result.passed,
      failed: result.failed,
      errors: result.errors,
      suitePassed: result.suitePassed,
      results: JSON.stringify(result.results),
      duration: result.duration,
      triggeredBy,
    },
  });

  return result;
}

/**
 * Get test results history for a policy.
 */
export async function getTestResults(
  policyId: string,
  options?: { limit?: number; offset?: number },
): Promise<{ results: Array<{ id: string; version: string; totalTests: number; passed: number; failed: number; errors: number; suitePassed: boolean; duration: number; triggeredBy: string; createdAt: string }>; total: number }> {
  const [results, total] = await Promise.all([
    db.declPolicyTestResult.findMany({
      where: { policyId },
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 20,
      skip: options?.offset ?? 0,
    }),
    db.declPolicyTestResult.count({ where: { policyId } }),
  ]);

  return {
    results: results.map((r) => ({
      id: r.id,
      version: r.version,
      totalTests: r.totalTests,
      passed: r.passed,
      failed: r.failed,
      errors: r.errors,
      suitePassed: r.suitePassed,
      duration: r.duration,
      triggeredBy: r.triggeredBy,
      createdAt: r.createdAt.toISOString(),
    })),
    total,
  };
}
