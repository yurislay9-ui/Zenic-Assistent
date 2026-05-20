/**
 * Route Guard Map — Maps every API route to its required subscription feature.
 *
 * This is the SINGLE SOURCE OF TRUTH for which subscription tier is required
 * for each API endpoint. The feature gate middleware uses this map to enforce
 * access control at the route level.
 *
 * Format: { routePattern: { feature: string, methods?: string[], description?: string } }
 *
 * Routes NOT listed here are accessible to all authenticated users.
 * Subscription management routes (/api/v1/subscription/*) are intentionally
 * excluded — users must be able to manage their subscription regardless of tier.
 */

import { TIER_RANK, FEATURE_GATES, SubscriptionTierName } from './types';

// ─── Types ───

export interface RouteGuard {
  /** The feature gate required to access this route. */
  feature: string;
  /** HTTP methods that require this feature. Empty array or undefined = all methods. */
  methods?: string[];
  /** Optional description of what this route does. */
  description?: string;
}

// ─── Complete Route → Feature Mapping ───

/**
 * Complete route → feature mapping for all Zenic-Agents API endpoints.
 *
 * Routes are organized by module and map to features defined in FEATURE_GATES.
 */
export const ROUTE_GUARDS: Record<string, RouteGuard> = {
  // ═══════════════════════════════════════════════════════════════════
  // Core Pipeline
  // ═══════════════════════════════════════════════════════════════════
  '/api/v1/pipeline/execute': { feature: 'full_pipeline', description: 'Execute full 9-step pipeline' },
  '/api/v1/pipeline/classify': { feature: 'basic_pipeline', description: 'Classify intent (L1)' },
  '/api/v1/pipeline/extract': { feature: 'basic_pipeline', description: 'Extract entities (L3)' },

  // ═══════════════════════════════════════════════════════════════════
  // MCP Gateway (Phase 1)
  // ═══════════════════════════════════════════════════════════════════
  '/api/mcp/gateway': { feature: 'mcp_gateway', description: 'MCP Gateway engine' },
  '/api/mcp/gateway/approve': { feature: 'mcp_gateway', methods: ['POST'], description: 'Approve MCP tool execution' },
  '/api/mcp/gateway/deny': { feature: 'mcp_gateway', methods: ['POST'], description: 'Deny MCP tool execution' },
  '/api/mcp/servers': { feature: 'mcp_gateway', description: 'List MCP servers' },
  '/api/mcp/servers/[id]': { feature: 'mcp_gateway', description: 'Get MCP server details' },
  '/api/mcp/tools': { feature: 'mcp_gateway', description: 'List MCP tools' },
  '/api/mcp/tools/[id]': { feature: 'mcp_gateway', description: 'Get MCP tool details' },
  '/api/v1/mcp/call': { feature: 'mcp_gateway', methods: ['POST'], description: 'Execute MCP tool call' },
  '/api/v1/mcp/tools': { feature: 'mcp_gateway', description: 'List MCP tools (v1)' },
  '/api/v1/mcp/tools/register': { feature: 'mcp_tools_register', methods: ['POST'], description: 'Register custom MCP tool' },
  '/api/v1/mcp/initialize': { feature: 'mcp_gateway', methods: ['POST'], description: 'Initialize MCP session' },

  // ═══════════════════════════════════════════════════════════════════
  // RBAC
  // ═══════════════════════════════════════════════════════════════════
  '/api/rbac/check': { feature: 'rbac_basic', description: 'Check RBAC permissions' },
  '/api/rbac/assign': { feature: 'rbac_full', methods: ['POST'], description: 'Assign role to user' },
  '/api/rbac/revoke': { feature: 'rbac_full', methods: ['POST'], description: 'Revoke role from user' },
  '/api/rbac/roles': { feature: 'rbac_basic', description: 'List/manage roles' },
  '/api/rbac/roles/[id]': { feature: 'rbac_basic', description: 'Get role details' },
  '/api/rbac/permissions': { feature: 'rbac_basic', description: 'List permissions' },

  // ═══════════════════════════════════════════════════════════════════
  // Observability (Phase 2)
  // ═══════════════════════════════════════════════════════════════════
  '/api/v1/observability/traces': { feature: 'observability_basic', description: 'List traces' },
  '/api/v1/observability/traces/[id]': { feature: 'observability_basic', description: 'Get trace details' },
  '/api/v1/observability/spans': { feature: 'observability_basic', description: 'List spans' },
  '/api/v1/observability/metrics': { feature: 'observability_basic', description: 'Get metrics' },
  '/api/v1/observability/metrics/business': { feature: 'observability_basic', description: 'Business metrics' },
  '/api/v1/observability/metrics/security': { feature: 'observability_basic', description: 'Security metrics' },
  '/api/v1/observability/metrics/resilience': { feature: 'observability_basic', description: 'Resilience metrics' },
  '/api/v1/observability/export/json': { feature: 'observability_export', methods: ['POST'], description: 'Export as JSON' },
  '/api/v1/observability/export/otel': { feature: 'observability_export', methods: ['POST'], description: 'Export as OpenTelemetry' },

  // ═══════════════════════════════════════════════════════════════════
  // Playbooks (Phase 3)
  // ═══════════════════════════════════════════════════════════════════
  '/api/v1/playbooks': { feature: 'playbook_library', description: 'List playbooks' },
  '/api/v1/playbooks/[playbookId]': { feature: 'playbook_library', description: 'Get playbook details' },
  '/api/v1/playbooks/activate': { feature: 'playbook_custom', methods: ['POST'], description: 'Activate playbook' },
  '/api/v1/playbooks/roi': { feature: 'playbook_roi', description: 'ROI calculation' },
  '/api/v1/playbooks/compliance': { feature: 'playbook_roi', description: 'Compliance report' },
  '/api/v1/playbooks/evaluate': { feature: 'playbook_library', description: 'Evaluate playbook' },
  '/api/v1/playbooks/seed': { feature: 'playbook_custom', methods: ['POST'], description: 'Seed playbook' },
  '/api/v1/playbooks/certification': { feature: 'playbook_library', description: 'Certification status' },
  '/api/v1/playbooks/metrics': { feature: 'playbook_roi', description: 'Operational metrics' },
  '/api/v1/playbooks/pricing': { feature: 'playbook_library', description: 'Playbook pricing' },
  '/api/v1/playbooks/onboarding': { feature: 'playbook_library', description: 'Onboarding wizard' },

  // ═══════════════════════════════════════════════════════════════════
  // Policy Engine (Phase 4)
  // ═══════════════════════════════════════════════════════════════════
  '/api/policies': { feature: 'policy_engine_basic', description: 'List/create policies' },
  '/api/policies/[id]': { feature: 'policy_engine_basic', description: 'Get/update/delete policy' },
  '/api/v1/policies': { feature: 'policy_engine_basic', description: 'List/create policies (v1)' },
  '/api/v1/policies/[policyId]': { feature: 'policy_engine_basic', description: 'Policy CRUD (v1)' },
  '/api/v1/policies/compliance': { feature: 'policy_compliance_mapping', description: 'Compliance mapping' },
  '/api/v1/policies/seed': { feature: 'policy_engine_full', methods: ['POST'], description: 'Seed policies' },
  '/api/v1/policies/hot-reload': { feature: 'policy_versioning', methods: ['POST'], description: 'Hot-reload policies' },
  '/api/v1/policies/versions': { feature: 'policy_versioning', description: 'Policy versioning' },
  '/api/v1/policies/evaluate': { feature: 'policy_engine_basic', methods: ['POST'], description: 'Evaluate policy' },
  '/api/v1/policies/diff': { feature: 'policy_versioning', description: 'Policy diff' },
  '/api/v1/policies/tests': { feature: 'policy_simulation', description: 'Policy test results' },

  // ═══════════════════════════════════════════════════════════════════
  // Policy Engine Advanced (Phase 4+)
  // ═══════════════════════════════════════════════════════════════════
  '/api/v1/policy-engine/verify': { feature: 'policy_engine_full', methods: ['POST'], description: 'Verify policy constraints' },
  '/api/v1/policy-engine/composition': { feature: 'policy_engine_full', description: 'Policy composition' },
  '/api/v1/policy-engine/composition/[setId]': { feature: 'policy_engine_full', description: 'Policy set details' },
  '/api/v1/policy-engine/composition/[setId]/compose': { feature: 'policy_engine_full', methods: ['POST'], description: 'Compose policy set' },
  '/api/v1/policy-engine/namespaces': { feature: 'policy_engine_full', description: 'Policy namespaces' },
  '/api/v1/policy-engine/namespaces/[namespaceId]': { feature: 'policy_engine_full', description: 'Namespace details' },
  '/api/v1/policy-engine/namespaces/[namespaceId]/evaluate': { feature: 'policy_engine_full', methods: ['POST'], description: 'Evaluate in namespace' },
  '/api/v1/policy-engine/namespaces/[namespaceId]/hierarchy': { feature: 'policy_engine_full', description: 'Namespace hierarchy' },
  '/api/v1/policy-engine/impact': { feature: 'policy_simulation', methods: ['POST'], description: 'Impact analysis' },
  '/api/v1/policy-engine/conflicts': { feature: 'policy_conflict_detection', description: 'Conflict detection' },
  '/api/v1/policy-engine/conflicts/[conflictId]/resolve': { feature: 'policy_conflict_detection', methods: ['POST'], description: 'Resolve conflict' },
  '/api/v1/policy-engine/templates': { feature: 'policy_engine_full', description: 'Policy templates' },
  '/api/v1/policy-engine/templates/[templateId]': { feature: 'policy_engine_full', description: 'Template details' },
  '/api/v1/policy-engine/templates/[templateId]/instantiate': { feature: 'policy_engine_full', methods: ['POST'], description: 'Instantiate template' },
  '/api/v1/policy-engine/simulations': { feature: 'policy_simulation', description: 'Policy simulations' },
  '/api/v1/policy-engine/simulations/[simulationId]': { feature: 'policy_simulation', description: 'Simulation details' },
  '/api/v1/policy-engine/approvals': { feature: 'policy_engine_full', description: 'Policy approvals' },
  '/api/v1/policy-engine/approvals/[approvalId]': { feature: 'policy_engine_full', description: 'Approval details' },
  '/api/v1/policy-engine/approvals/[approvalId]/deploy': { feature: 'policy_versioning', methods: ['POST'], description: 'Deploy approval' },
  '/api/v1/policy-engine/approvals/[approvalId]/review': { feature: 'policy_engine_full', methods: ['POST'], description: 'Review approval' },
  '/api/v1/policy-engine/approvals/[approvalId]/decide': { feature: 'policy_engine_full', methods: ['POST'], description: 'Decide on approval' },

  // ═══════════════════════════════════════════════════════════════════
  // HITL (Phase 5)
  // ═══════════════════════════════════════════════════════════════════
  '/api/v1/hitl': { feature: 'hitl_approvals', description: 'List HITL approvals' },
  '/api/v1/hitl/stats': { feature: 'hitl_approvals', description: 'HITL stats' },
  '/api/v1/hitl/[requestId]': { feature: 'hitl_approvals', description: 'Get approval request' },
  '/api/v1/hitl/[requestId]/approve': { feature: 'hitl_approvals', methods: ['POST'], description: 'Approve request' },
  '/api/v1/hitl/[requestId]/reject': { feature: 'hitl_approvals', methods: ['POST'], description: 'Reject request' },
  '/api/v1/hitl/[requestId]/undo': { feature: 'hitl_reversible_actions', methods: ['POST'], description: 'Undo action' },
  '/api/v1/hitl/[requestId]/escalate': { feature: 'hitl_escalation', methods: ['POST'], description: 'Escalate request' },
  '/api/v1/hitl/[requestId]/delegate': { feature: 'hitl_delegation', methods: ['POST'], description: 'Delegate request' },
  '/api/v1/hitl/pending': { feature: 'hitl_approvals', description: 'List pending approvals' },
  '/api/v1/hitl/history': { feature: 'hitl_approvals', description: 'Approval history' },
  '/api/v1/hitl/delegations': { feature: 'hitl_delegation', description: 'List delegations' },
  '/api/v1/hitl/evidence': { feature: 'hitl_evidence', description: 'Evidence list' },
  '/api/v1/hitl/evidence/[requestId]': { feature: 'hitl_evidence', description: 'Evidence for request' },
  '/api/v1/hitl/justification': { feature: 'hitl_approvals', description: 'Justification list' },
  '/api/v1/hitl/justification/[requestId]': { feature: 'hitl_approvals', description: 'Justification for request' },
  '/api/v1/hitl/sla/[requestId]': { feature: 'hitl_sla_tracking', description: 'SLA for request' },
  '/api/v1/hitl/sla/check': { feature: 'hitl_sla_tracking', description: 'Check SLA compliance' },
  '/api/v1/hitl/expiry/[requestId]': { feature: 'hitl_approvals', description: 'Expiry for request' },
  '/api/v1/hitl/expiry/check': { feature: 'hitl_approvals', description: 'Check expirations' },
  '/api/v1/hitl/notifications/[userId]': { feature: 'hitl_approvals', description: 'Notifications for user' },
  '/api/v1/hitl/pipeline/create': { feature: 'hitl_approvals', methods: ['POST'], description: 'Create from pipeline' },
  '/api/v1/hitl/coordinator/create': { feature: 'hitl_approvals', methods: ['POST'], description: 'Create via coordinator' },
  '/api/v1/hitl/coordinator/approve': { feature: 'hitl_approvals', methods: ['POST'], description: 'Coordinator approve' },
  '/api/v1/hitl/coordinator/reject': { feature: 'hitl_approvals', methods: ['POST'], description: 'Coordinator reject' },

  // ═══════════════════════════════════════════════════════════════════
  // Dashboard / Metrics
  // ═══════════════════════════════════════════════════════════════════
  '/api/dashboard/metrics': { feature: 'basic_pipeline', description: 'Dashboard metrics' },
  '/api/dashboard/metrics/route': { feature: 'basic_pipeline', description: 'Dashboard metrics route' },

  // ═══════════════════════════════════════════════════════════════════
  // Audit
  // ═══════════════════════════════════════════════════════════════════
  '/api/audit': { feature: 'basic_pipeline', description: 'Audit log' },

  // ═══════════════════════════════════════════════════════════════════
  // Users
  // ═══════════════════════════════════════════════════════════════════
  '/api/users': { feature: 'basic_pipeline', description: 'User management' },

  // ═══════════════════════════════════════════════════════════════════
  // Seed
  // ═══════════════════════════════════════════════════════════════════
  '/api/seed': { feature: 'basic_pipeline', description: 'Database seeding' },

  // NOTE: /api/v1/subscription/* routes are intentionally NOT gated.
  // Users must be able to manage their subscription (signup, upgrade,
  // check features, etc.) regardless of their current tier.
  // The root /api route is also not gated (health check / welcome).
};

// ─── Dynamic Route Matching ───

/**
 * Finds the route guard for a given request path and HTTP method.
 *
 * Tries exact match first, then falls back to dynamic segment matching
 * for patterns like [id], [requestId], [tenantId], etc.
 *
 * @param pathname - The request pathname (e.g. "/api/v1/hitl/abc-123/approve")
 * @param method   - The HTTP method (e.g. "GET", "POST"). Defaults to "GET".
 * @returns The matching RouteGuard, or null if the route is not gated.
 */
export function findRouteGuard(pathname: string, method: string = 'GET'): RouteGuard | null {
  // Try exact match first
  const exact = ROUTE_GUARDS[pathname];
  if (exact) {
    if (exact.methods && exact.methods.length > 0 && !exact.methods.includes(method.toUpperCase())) {
      return null; // Method not gated for this route
    }
    return exact;
  }

  // Try dynamic segment matching
  for (const [pattern, guard] of Object.entries(ROUTE_GUARDS)) {
    if (matchDynamicRoute(pattern, pathname)) {
      if (guard.methods && guard.methods.length > 0 && !guard.methods.includes(method.toUpperCase())) {
        return null;
      }
      return guard;
    }
  }

  // No guard found — route is accessible to all authenticated users
  return null;
}

/**
 * Matches a dynamic route pattern against a concrete pathname.
 *
 * E.g., pattern "/api/v1/hitl/[requestId]/approve" matches
 *        pathname  "/api/v1/hitl/abc-123/approve"
 */
function matchDynamicRoute(pattern: string, pathname: string): boolean {
  const patternParts = pattern.split('/');
  const pathParts = pathname.split('/');

  if (patternParts.length !== pathParts.length) {
    return false;
  }

  for (let i = 0; i < patternParts.length; i++) {
    const patternPart = patternParts[i];
    const pathPart = pathParts[i];

    // Dynamic segment like [id], [requestId], [tenantId], etc.
    if (patternPart.startsWith('[') && patternPart.endsWith(']')) {
      continue; // Matches any non-empty value
    }

    if (patternPart !== pathPart) {
      return false;
    }
  }

  return true;
}

// ─── Tier-based Route Queries ───

/**
 * Returns all routes that are available for a specific subscription tier.
 *
 * @param tier - The subscription tier name
 * @returns Array of route patterns available for the tier
 */
export function getRoutesForTier(tier: SubscriptionTierName): string[] {
  const tierRank = TIER_RANK[tier] ?? 0;

  return Object.entries(ROUTE_GUARDS)
    .filter(([_, guard]) => {
      const gate = FEATURE_GATES.find(g => g.feature === guard.feature);
      if (!gate) return false;
      return tierRank >= (TIER_RANK[gate.minimumTier] ?? Infinity);
    })
    .map(([route]) => route);
}

/**
 * Returns all routes that are NOT available for a given tier,
 * along with the minimum tier required to access each.
 *
 * @param tier - The subscription tier name
 * @returns Array of restricted routes with required tier info
 */
export function getRestrictedRoutesForTier(
  tier: SubscriptionTierName
): Array<{ route: string; requiredTier: string; feature: string }> {
  const tierRank = TIER_RANK[tier] ?? 0;

  return Object.entries(ROUTE_GUARDS)
    .filter(([_, guard]) => {
      const gate = FEATURE_GATES.find(g => g.feature === guard.feature);
      if (!gate) return true; // Unknown gate = restricted
      return tierRank < (TIER_RANK[gate.minimumTier] ?? Infinity);
    })
    .map(([route, guard]) => {
      const gate = FEATURE_GATES.find(g => g.feature === guard.feature);
      return {
        route,
        requiredTier: gate?.minimumTier ?? 'unknown',
        feature: guard.feature,
      };
    });
}

/**
 * Returns a summary of route counts per feature gate.
 * Useful for debugging and documentation.
 */
export function getRouteGuardSummary(): Record<string, { count: number; routes: string[] }> {
  const summary: Record<string, { count: number; routes: string[] }> = {};

  for (const [route, guard] of Object.entries(ROUTE_GUARDS)) {
    if (!summary[guard.feature]) {
      summary[guard.feature] = { count: 0, routes: [] };
    }
    summary[guard.feature].count++;
    summary[guard.feature].routes.push(route);
  }

  return summary;
}
