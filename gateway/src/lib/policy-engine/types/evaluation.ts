// ─── Policy Test Results ──────────────────────────────────────────────

/** Result of running a single test case */
export interface PolicyTestResult {
  /** Test case name */
  testName: string;
  /** Whether the test passed */
  passed: boolean;
  /** Expected outcome */
  expected: PolicyTestExpectation;
  /** Actual outcome */
  actual: PolicyTestExpectation;
  /** The statement that matched (if any) */
  matchedStatementId?: string;
  /** Error message (if test errored) */
  error?: string;
  /** Evaluation context snapshot */
  evaluationDetails?: PolicyEvaluationResult;
}

/** Result of running all tests for a policy */
export interface PolicyTestSuiteResult {
  /** Policy ID */
  policyId: string;
  /** Policy version tested */
  version: string;
  /** Total tests */
  total: number;
  /** Passed tests */
  passed: number;
  /** Failed tests */
  failed: number;
  /** Errored tests */
  errors: number;
  /** Individual test results */
  results: PolicyTestResult[];
  /** Execution time in ms */
  duration: number;
  /** Whether the suite passed overall */
  suitePassed: boolean;
}

// ─── Policy Evaluation ────────────────────────────────────────────────

/** A request to evaluate against policies */
export interface PolicyEvaluationRequest {
  /** Resource being accessed (e.g., "financial/transfer") */
  resource: string;
  /** Action being performed (e.g., "execute") */
  action: string;
  /** Evaluation context (field values for conditions) */
  context: Record<string, unknown>;
  /** Tenant ID (for multi-tenant) */
  tenantId?: string;
  /** Requesting user ID */
  userId?: string;
  /** Requesting user roles */
  roles?: string[];
}

/** Result of policy evaluation */
export interface PolicyEvaluationResult {
  /** Final effect */
  effect: PolicyEffectV2;
  /** The policy that determined the outcome */
  policyId: string;
  /** The specific statement that matched */
  matchedStatementId?: string;
  /** Human-readable reason */
  reason: string;
  /** All matched statements (for audit) */
  matchedStatements: Array<{
    policyId: string;
    statementId: string;
    effect: PolicyEffectV2;
    priority: number;
  }>;
  /** Evaluation duration in ms */
  duration: number;
  /** Whether this was a deny-by-default */
  denyByDefault: boolean;
  /** Required role (if conditional) */
  requiredRole?: string;
}

