   */
  private invalidateCache(playbookId: string): void {
    this.cache.delete(playbookId);
  }
}

// ─── DB Record Mapping ───────────────────────────────────────────────

/** Flattened playbook record with parsed JSON fields */
export interface PlaybookDbRecord {
  id: string;
  playbookId: string;
  name: string;
  nameEn: string;
  industry: string;
  subIndustry: string;
  apiVersion: string;
  version: string;
  description: string;
  icon: string;
  color: string;
  labels: Record<string, string>;
  compliance: string[];
  capabilities: PlaybookCapability[];
  policies: PolicyReference[];
  roiConfig: PlaybookRoiConfig;
  pricing: PlaybookPricing;
  onboarding: PlaybookOnboardingConfig;
  certificationStatus: string;
  certificationSignedBy: string | null;
  certificationSignedAt: Date | null;
  certificationSignature: string | null;
  certificationHash: string | null;
  sourceYaml: string | null;
  contentHash: string;
  isActive: boolean;
  author: string | null;
  createdAt: Date;
  updatedAt: Date;
  /** Reconstructed PlaybookDocument */
  document: PlaybookDocument;
}

/**
 * Map a Prisma Playbook record to a PlaybookDbRecord with parsed JSON fields.
 */
function mapDbToRecord(p: {
  id: string;
  playbookId: string;
  name: string;
  nameEn: string | null;
  industry: string;
  subIndustry: string | null;
  apiVersion: string;
  version: string;
  description: string;
  icon: string | null;
  color: string | null;
  labels: string;
  compliance: string;
  capabilities: string;
  policies: string;
  roiConfig: string;
  pricing: string;
  onboarding: string;
  certificationStatus: string;
  certificationSignedBy: string | null;
  certificationSignedAt: Date | null;
  certificationSignature: string | null;
  certificationHash: string | null;
  sourceYaml: string | null;
  contentHash: string;
  isActive: boolean;
  author: string | null;
  createdAt: Date;
  updatedAt: Date;
}): PlaybookDbRecord {
  const capabilities: PlaybookCapability[] = JSON.parse(p.capabilities);
  const policies: PolicyReference[] = JSON.parse(p.policies);
  const roiConfig: PlaybookRoiConfig = JSON.parse(p.roiConfig);
  const pricing: PlaybookPricing = JSON.parse(p.pricing);
  const onboarding: PlaybookOnboardingConfig = JSON.parse(p.onboarding);
  const labels: Record<string, string> = JSON.parse(p.labels);
  const compliance: string[] = JSON.parse(p.compliance);

  const certification: PlaybookCertification = {
    status: p.certificationStatus as CertificationStatus,
    signedBy: p.certificationSignedBy ?? undefined,
    signedAt: p.certificationSignedAt?.toISOString(),
    signature: p.certificationSignature ?? undefined,
    contentHash: p.certificationHash ?? undefined,
  };

  const document: PlaybookDocument = {
    apiVersion: p.apiVersion as typeof import("./types").PLAYBOOK_API_VERSION,
    kind: "Playbook" as const,
    metadata: {
      id: p.playbookId,
      name: p.name,
      name_en: p.nameEn ?? p.name,
      industry: p.industry as Industry,
      sub_industry: p.subIndustry ?? "",
      compliance,
      icon: p.icon ?? "📋",
      color: p.color ?? "#6b7280",
      version: p.version,
      description: p.description,
      author: p.author ?? "system",
      labels,
    },
    capabilities,
    policies,
    roi: roiConfig,
    pricing,
    onboarding,
    certification,
  };

  return {
    id: p.id,
    playbookId: p.playbookId,
    name: p.name,
    nameEn: p.nameEn ?? p.name,
    industry: p.industry,
    subIndustry: p.subIndustry ?? "",
    apiVersion: p.apiVersion,
    version: p.version,
    description: p.description,
    icon: p.icon ?? "📋",
    color: p.color ?? "#6b7280",
    labels,
    compliance,
    capabilities,
    policies,
    roiConfig,
    pricing,
    onboarding,
    certificationStatus: p.certificationStatus,
    certificationSignedBy: p.certificationSignedBy,
    certificationSignedAt: p.certificationSignedAt,
    certificationSignature: p.certificationSignature,
    certificationHash: p.certificationHash,
    sourceYaml: p.sourceYaml,
    contentHash: p.contentHash,
    isActive: p.isActive,
    author: p.author,
    createdAt: p.createdAt,
    updatedAt: p.updatedAt,
    document,
  };
}

// ─── Inline ROI Calculation (fallback) ────────────────────────────────

function calculateRoiInline(
  baseline: RoiBaseline,
  projected: RoiProjected,
  monthlyCostUsd: number,
): RoiCalculation {
  const workingHoursPerMonth = 160;
  const hourlyCostUsd = 50;

  const timeSavedPerActionMin = baseline.manual_time_per_action_min - projected.automated_time_per_action_min;
  const automatedActionsPerMonth = baseline.actions_per_month * (projected.automation_rate_pct / 100);
  const time_saved_hours_month = (timeSavedPerActionMin * automatedActionsPerMonth) / 60;

  const originalErrorsPerMonth = baseline.actions_per_month * (baseline.error_rate_pct / 100);
  const newErrorsPerMonth = automatedActionsPerMonth * (projected.reduced_error_rate_pct / 100);
  const errors_avoided_month = originalErrorsPerMonth - newErrorsPerMonth;

  const violationReductionPct = Math.max(0, projected.compliance_score_target - (100 - baseline.error_rate_pct * 5));
  const compliance_risk_reduction_usd = baseline.violations_per_year * baseline.penalty_per_violation_usd * (violationReductionPct / 100);

  const timeSavingsAnnual = time_saved_hours_month * hourlyCostUsd * 12;
  const errorSavingsAnnual = errors_avoided_month * baseline.cost_per_error_usd * 12;
  const totalSavingsAnnual = timeSavingsAnnual + errorSavingsAnnual + compliance_risk_reduction_usd;
  const totalCostAnnual = monthlyCostUsd * 12;
  const net_roi_usd = totalSavingsAnnual - totalCostAnnual;

  const roi_percentage = totalCostAnnual > 0 ? (net_roi_usd / totalCostAnnual) * 100 : 0;
  const monthlySavings = totalSavingsAnnual / 12;
  const payback_months = monthlySavings > 0 ? Math.ceil(totalCostAnnual / monthlySavings) : 999;

  return {
    time_saved_hours_month: Math.round(time_saved_hours_month * 100) / 100,
    errors_avoided_month: Math.round(errors_avoided_month * 100) / 100,
    compliance_risk_reduction_usd: Math.round(compliance_risk_reduction_usd * 100) / 100,
    net_roi_usd: Math.round(net_roi_usd * 100) / 100,
    roi_percentage: Math.round(roi_percentage * 100) / 100,
    payback_months,
  };
}

function createDefaultRoiCalculation(): RoiCalculation {
  return {
    time_saved_hours_month: 0,
    errors_avoided_month: 0,
    compliance_risk_reduction_usd: 0,
    net_roi_usd: 0,
    roi_percentage: 0,
    payback_months: 999,
  };
}

// ─── Lazy Module Loaders ──────────────────────────────────────────────

let roiCalculatorModule: RoiCalculatorModule | null = null;

async function loadRoiCalculator(): Promise<RoiCalculatorModule> {
  if (roiCalculatorModule) return roiCalculatorModule;

  try {
    // Dynamic import — will resolve once the roi-calculator module exists
    const mod = await import("@/lib/playbooks/roi-calculator") as unknown;
    roiCalculatorModule = mod as RoiCalculatorModule;
    return roiCalculatorModule;
  } catch {
    // Module not available — create inline fallback
    roiCalculatorModule = {
      calculateRoi: (input) =>
        calculateRoiInline(input.baseline, input.projected, input.monthlyCostUsd),
    };
    return roiCalculatorModule;
  }
}

let pricingEngineModule: PricingEngineModule | null = null;

async function loadPricingEngine(): Promise<PricingEngineModule> {
  if (pricingEngineModule) return pricingEngineModule;

  try {
    const mod = await import("@/lib/playbooks/pricing-engine") as unknown;
    pricingEngineModule = mod as PricingEngineModule;
    return pricingEngineModule;
  } catch {
    pricingEngineModule = {
      calculatePricing: (input) => {
        const tier = input.pricing.tiers.find((t) => t.name === input.selectedTier);
        const monthly_cost_usdt = tier?.price_usdt ?? 0;
        const setup_fee_usdt = tier?.setup_fee_usdt ?? 0;
        return {
          selected_tier: input.selectedTier,
          monthly_cost_usdt,
          annual_cost_usdt: monthly_cost_usdt * 10,
          setup_fee_usdt,
          per_action_cost: input.actionsPerMonth > 0 ? monthly_cost_usdt / input.actionsPerMonth : 0,
          break_even_actions: 0,
          payment_currency: "USDT",
          payment_network: "TRC20",
        };
      },
    };
    return pricingEngineModule;
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

let engineInstance: PlaybookEngine | null = null;

export function getPlaybookEngine(config?: Partial<PlaybookEngineConfig>): PlaybookEngine {
  if (!engineInstance) {
    engineInstance = new PlaybookEngine(config);
  }
  return engineInstance;
}

export function resetPlaybookEngine(): void {
  engineInstance = null;
  roiCalculatorModule = null;
  pricingEngineModule = null;
}
