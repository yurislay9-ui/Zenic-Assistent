// ─── Zenic-Agents v3 — Playbook YAML Loader: Compiler — Struct ─────────
// Pricing, onboarding, and certification compilation helpers.

import {
  CertificationStatus,
  PricingTierName,
  type PlaybookPricing,
  type PricingTier,
  type PlaybookOnboardingConfig,
  type OnboardingStep,
  type PlaybookCertification,
  type OnboardingStepType,
} from "../types";

import {
  PlaybookValidationError,
  type PlaybookYamlLoaderConfig,
  VALID_STEP_TYPES,
  VALID_TIER_NAMES,
  VALID_CERTIFICATION_STATUSES,
} from "./types";

// ─── Pricing Compilation ──────────────────────────────────────────────

export function compilePricing(
  raw: unknown,
  config: PlaybookYamlLoaderConfig,
): PlaybookPricing {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("pricing must be an object", "pricing");
  }

  const obj = raw as Record<string, unknown>;

  // Support two YAML formats:
  // 1. Array format: pricing.tiers: [{ name: starter, ... }, ...]
  // 2. Nested format: pricing.starter: { ... }, pricing.pro: { ... }, pricing.enterprise: { ... }
  let tiers: PricingTier[];

  if (Array.isArray(obj.tiers)) {
    // Format 1: Array-based tiers
    tiers = obj.tiers.map((t: unknown, i: number) =>
      compilePricingTier(t, i, config),
    );
  } else {
    // Format 2: Nested key-based tiers (starter, pro, enterprise as separate objects)
    const nestedTiers: PricingTier[] = [];
    const tierKeys = [PricingTierName.STARTER, PricingTierName.BUSINESS, PricingTierName.ENTERPRISE, PricingTierName.ON_PREMISE_ENTERPRISE, PricingTierName.TRIAL];

    for (const key of tierKeys) {
      const tierData = obj[key];
      if (tierData && typeof tierData === "object") {
        // Inject the name from the key if not present
        const tierObj = { ...(tierData as Record<string, unknown>), name: key };
        nestedTiers.push(compilePricingTier(tierObj, nestedTiers.length, config));
      }
    }

    tiers = nestedTiers;
  }

  // Check that starter and business tiers exist
  const tierNames = tiers.map((t) => t.name);
  if (!tierNames.includes(PricingTierName.STARTER) || !tierNames.includes(PricingTierName.BUSINESS)) {
    throw new PlaybookValidationError(
      "pricing.tiers must include both 'starter' and 'business' tiers",
      "pricing.tiers",
    );
  }

  return {
    currency: typeof obj.currency === "string" ? obj.currency : "USDT",
    network: typeof obj.network === "string" ? obj.network : "TRC20",
    tiers,
  };
}

function compilePricingTier(
  raw: unknown,
  index: number,
  config: PlaybookYamlLoaderConfig,
): PricingTier {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`pricing.tiers[${index}] must be an object`, `pricing.tiers[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `pricing.tiers[${index}]`;

  // Validate tier name
  const name = typeof obj.name === "string" ? obj.name : "";
  if (config.strictValidation && !VALID_TIER_NAMES.has(name)) {
    throw new PlaybookValidationError(
      `${prefix}.name must be one of: ${[...VALID_TIER_NAMES].join(", ")}`,
      `${prefix}.name`,
      name,
    );
  }

  return {
    name: name as PricingTier["name"],
    price_usdt: typeof obj.price_usdt === "number" ? obj.price_usdt : (typeof obj.price_usd === "number" ? obj.price_usd : 0),
    setup_fee_usdt: typeof obj.setup_fee_usdt === "number" ? obj.setup_fee_usdt : 0,
    features: Array.isArray(obj.features) ? obj.features.map(String) : [],
    limits: obj.limits && typeof obj.limits === "object"
      ? obj.limits as Record<string, number | "unlimited">
      : {},
    recommended_for: typeof obj.recommended_for === "string" ? obj.recommended_for : "",
    payment_currency: typeof obj.payment_currency === "string" ? obj.payment_currency : "USDT",
    payment_network: typeof obj.payment_network === "string" ? obj.payment_network : "TRC20",
  };
}

// ─── Onboarding Compilation ───────────────────────────────────────────

export function compileOnboarding(
  raw: unknown,
  _config: PlaybookYamlLoaderConfig,
): PlaybookOnboardingConfig {
  if (!raw || typeof raw !== "object") {
    // Default onboarding config
    return {
      steps: [],
      estimated_minutes: 15,
    };
  }

  const obj = raw as Record<string, unknown>;

  const steps = Array.isArray(obj.steps)
    ? obj.steps.map((s: unknown, i: number) => compileOnboardingStep(s, i))
    : [];

  return {
    steps,
    estimated_minutes: typeof obj.estimated_minutes === "number" ? obj.estimated_minutes : 15,
  };
}

function compileOnboardingStep(
  raw: unknown,
  index: number,
): OnboardingStep {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError(`onboarding.steps[${index}] must be an object`, `onboarding.steps[${index}]`);
  }

  const obj = raw as Record<string, unknown>;
  const prefix = `onboarding.steps[${index}]`;

  // Validate step type
  const type = typeof obj.type === "string" ? obj.type : "question";
  if (!VALID_STEP_TYPES.has(type)) {
    throw new PlaybookValidationError(
      `${prefix}.type must be one of: ${[...VALID_STEP_TYPES].join(", ")}`,
      `${prefix}.type`,
      type,
    );
  }

  // Compile options for selection steps
  let options: OnboardingStep["options"];
  if (Array.isArray(obj.options)) {
    options = obj.options.map((o: unknown) => {
      if (!o || typeof o !== "object") {
        throw new PlaybookValidationError(`${prefix}.options must contain objects`, `${prefix}.options`);
      }
      const opt = o as Record<string, unknown>;
      return {
        value: typeof opt.value === "string" ? opt.value : String(opt.value ?? ""),
        label: typeof opt.label === "string" ? opt.label : String(opt.value ?? ""),
        default: typeof opt.default === "boolean" ? opt.default : undefined,
      };
    });
  }

  return {
    id: typeof obj.id === "string" ? obj.id : `step-${index}`,
    title: typeof obj.title === "string" ? obj.title : `Step ${index + 1}`,
    description: typeof obj.description === "string" ? obj.description : "",
    type: type as OnboardingStepType,
    field: typeof obj.field === "string" ? obj.field : `field_${index}`,
    options,
    default_value: obj.default_value ?? null,
    required: typeof obj.required === "boolean" ? obj.required : false,
  };
}

// ─── Certification Compilation ────────────────────────────────────────

export function compileCertification(
  raw: unknown,
  _config: PlaybookYamlLoaderConfig,
): PlaybookCertification {
  if (!raw || typeof raw !== "object") {
    return {
      status: CertificationStatus.UNSIGNED,
    };
  }

  const obj = raw as Record<string, unknown>;

  // Validate certification status
  const status = typeof obj.status === "string" ? obj.status : CertificationStatus.UNSIGNED;
  if (!VALID_CERTIFICATION_STATUSES.has(status)) {
    throw new PlaybookValidationError(
      `certification.status must be one of: ${[...VALID_CERTIFICATION_STATUSES].join(", ")}`,
      "certification.status",
      status,
    );
  }

  return {
    status: status as CertificationStatus,
    signedBy: typeof obj.signedBy === "string" ? obj.signedBy : undefined,
    signedAt: typeof obj.signedAt === "string" ? obj.signedAt : undefined,
    signature: typeof obj.signature === "string" ? obj.signature : undefined,
    contentHash: typeof obj.contentHash === "string" ? obj.contentHash : undefined,
  };
}
