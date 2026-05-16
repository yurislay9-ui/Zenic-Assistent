// ─── Zenic-Agents v3 — Subscription Features ───────────────────────────
// GET /api/v1/subscription/features?tenantId=xxx
// Get available features for tenant's tier.

import { db } from "@/lib/db";
import { getTierFeatures, PAYMENT_CURRENCY, PAYMENT_NETWORK } from "@/lib/pricing-engine";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const tenantId = searchParams.get("tenantId");

    if (!tenantId) {
      return Response.json(
        { error: "Missing required query parameter: tenantId" },
        { status: 400 }
      );
    }

    // Look up subscription tier
    const subscription = await db.subscription.findUnique({
      where: { tenantId },
      select: {
        subscriptionId: true,
        tier: true,
        status: true,
      },
    });

    if (!subscription) {
      return Response.json(
        {
          error: "No subscription found for this tenant",
          tenantId,
          hint: "Use /api/v1/subscription/trial to start a trial",
        },
        { status: 404 }
      );
    }

    // Check if subscription is active
    const activeStatuses = ["trial", "active"];
    if (!activeStatuses.includes(subscription.status)) {
      return Response.json(
        {
          error: "Subscription is not active",
          tenantId,
          subscriptionId: subscription.subscriptionId,
          status: subscription.status,
          hint: "Only active or trial subscriptions can access features.",
        },
        { status: 400 }
      );
    }

    // Use getTierFeatures from pricing engine
    const tierFeatures = getTierFeatures(subscription.tier);

    // Group features by category for better organization
    const categorized: Record<string, Array<{ feature: string; available: boolean; minimumTier: string | null }>> = {
      mcp: [],
      rbac: [],
      observability: [],
      policy: [],
      playbook: [],
      hitl: [],
      audit: [],
      executor: [],
      onPremise: [],
    };

    const featureCategories: Record<string, string[]> = {
      mcp: ["McpToolExecution", "McpCustomTools", "McpToolRegistration", "McpRateLimiting", "McpAuthApiKey", "McpAuthOAuth2", "McpAuthMTls", "McpMerkleAudit"],
      rbac: ["RbacBasicRoles", "RbacCustomRoles", "RbacDangerousPermApproval", "RbacSsoIntegration"],
      observability: ["ObservabilityTracing", "ObservabilityBusinessMetrics", "ObservabilitySecurityMetrics", "ObservabilityResilienceMetrics", "ObservabilityOtelExport", "ObservabilityJsonExport", "ObservabilityCustomDashboards"],
      policy: ["PolicyDeclarativeYaml", "PolicyVersioning", "PolicyTesting", "PolicyHotReload", "PolicyComplianceMapping", "PolicyComposition", "PolicyConflictDetection", "PolicyConstraintSolver", "PolicySimulation", "PolicyNamespaces", "PolicyTemplates", "PolicyApprovalWorkflow", "PolicyImpactAnalysis", "PolicyZ3Solver"],
      playbook: ["PlaybookActivation", "PlaybookCustomYaml", "PlaybookRoiCalculator", "PlaybookOnboardingWizard", "PlaybookCertification", "PlaybookComplianceMap"],
      hitl: ["HitlApprovalWorkflow", "HitlDelegation", "HitlEscalation", "HitlUndoReversible", "HitlEvidence", "HitlJustification", "HitlSlaTracking", "HitlAutoApprove", "HitlExpiryAutoRevert"],
      audit: ["AuditBasicLog", "AuditMerkleChain", "AuditComplianceExport"],
      executor: ["ExecutorBasic", "ExecutorData", "ExecutorStorage", "ExecutorSecurity", "ExecutorAdvanced", "ExecutorQueue", "ExecutorMonitoring"],
      onPremise: ["OnPremiseDeployment", "OnPremiseAirGap", "OnPremiseCustomBranding", "OnPremiseDataResidency"],
    };

    for (const feature of tierFeatures.features) {
      let placed = false;
      for (const [category, prefixes] of Object.entries(featureCategories)) {
        if (prefixes.includes(feature.feature)) {
          categorized[category].push({
            feature: feature.feature,
            available: feature.available,
            minimumTier: feature.minimum_tier,
          });
          placed = true;
          break;
        }
      }
      if (!placed) {
        categorized.mcp.push({
          feature: feature.feature,
          available: feature.available,
          minimumTier: feature.minimum_tier,
        });
      }
    }

    // Compute totals
    const totalFeatures = tierFeatures.features.length;
    const availableFeatures = tierFeatures.features.filter((f) => f.available).length;
    const unavailableFeatures = totalFeatures - availableFeatures;

    return Response.json({
      tenantId,
      subscription: {
        subscriptionId: subscription.subscriptionId,
        tier: subscription.tier,
        status: subscription.status,
      },
      tierFeatures: {
        tier: tierFeatures.tier,
        displayName: tierFeatures.display_name,
      },
      features: categorized,
      summary: {
        totalFeatures,
        availableFeatures,
        unavailableFeatures,
        coveragePercent: totalFeatures > 0 ? Math.round((availableFeatures / totalFeatures) * 100) : 0,
      },
      paymentCurrency: PAYMENT_CURRENCY,
      paymentNetwork: PAYMENT_NETWORK,
    });
  } catch (error) {
    console.error("[Subscription Features] Error:", error);
    return Response.json(
      { error: "Internal server error retrieving features" },
      { status: 500 }
    );
  }
}
