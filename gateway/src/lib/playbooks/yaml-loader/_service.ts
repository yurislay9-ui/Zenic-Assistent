// ─── Zenic-Agents v3 — YAML Loader Service ────────────────────────────
// Split from yaml-loader.ts — public API functions (load, compile, validate, hash, serialize)

import yaml from "js-yaml";
import { createHash } from "crypto";
import {
  PLAYBOOK_API_VERSION,
  PLAYBOOK_KIND,
  CertificationStatus as CertificationStatusEnum,
  PricingTierName as PricingTierNameEnum,
  type PlaybookDocument,
  type PlaybookValidationResult,
  type PlaybookValidationError as PlaybookValidationErrorCode,
} from "../types";
import {
  PlaybookValidationError,
  PlaybookCompilationError,
  DEFAULT_LOADER_CONFIG,
} from "./_types";
import type { PlaybookYamlLoaderConfig } from "./_types";
import { deepSortKeys } from "./_utils";
import {
  compileMetadata,
  compileCapability,
  compilePolicyReference,
  compileOnboarding,
  compileCertification,
} from "./_compilers-core";
import {
  compileRoiConfig,
  compilePricing,
} from "./_compilers-roi-pricing";

// ─── Core Loader Functions ────────────────────────────────────────────

/**
 * Parse a YAML string into a PlaybookDocument.
 * Validates structure and semantics according to playbook.zenic.dev/v1 spec.
 */
export function loadPlaybookFromYaml(
  yamlContent: string,
  config: Partial<PlaybookYamlLoaderConfig> = {},
): PlaybookDocument {
  const cfg = { ...DEFAULT_LOADER_CONFIG, ...config };

  let raw: unknown;
  try {
    raw = yaml.load(yamlContent, { schema: yaml.DEFAULT_SAFE_SCHEMA });
  } catch (err) {
    throw new PlaybookCompilationError(
      `YAML parse error: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  return compilePlaybookDocument(raw, cfg);
}

/**
 * Validate and compile a raw object into a PlaybookDocument.
 */
export function compilePlaybookDocument(
  raw: unknown,
  config: PlaybookYamlLoaderConfig = DEFAULT_LOADER_CONFIG,
): PlaybookDocument {
  if (!raw || typeof raw !== "object") {
    throw new PlaybookValidationError("Playbook document must be an object", "root");
  }

  const obj = raw as Record<string, unknown>;

  if (obj.apiVersion !== PLAYBOOK_API_VERSION) {
    if (config.strictValidation) {
      throw new PlaybookValidationError(
        `Invalid apiVersion "${String(obj.apiVersion)}". Expected "${PLAYBOOK_API_VERSION}"`,
        "apiVersion",
        obj.apiVersion,
      );
    }
  }

  if (obj.kind !== PLAYBOOK_KIND) {
    if (config.strictValidation) {
      throw new PlaybookValidationError(
        `Invalid kind "${String(obj.kind)}". Expected "${PLAYBOOK_KIND}"`,
        "kind",
        obj.kind,
      );
    }
  }

  const metadata = compileMetadata(obj.metadata, config);

  if (!Array.isArray(obj.capabilities) || obj.capabilities.length === 0) {
    throw new PlaybookValidationError(
      "Playbook must have at least one capability",
      "capabilities",
    );
  }
  const capabilities = obj.capabilities.map((c: unknown, i: number) =>
    compileCapability(c, i, config),
  );

  const policies = Array.isArray(obj.policies)
    ? obj.policies.map((p: unknown, i: number) => compilePolicyReference(p, i, config))
    : [];

  const roi = compileRoiConfig(obj.roi, config);
  const pricing = compilePricing(obj.pricing, config);
  const onboarding = compileOnboarding(obj.onboarding, config);
  const certification = compileCertification(obj.certification, config);

  return {
    apiVersion: PLAYBOOK_API_VERSION,
    kind: PLAYBOOK_KIND,
    metadata,
    capabilities,
    policies,
    roi,
    pricing,
    onboarding,
    certification,
  };
}

// ─── Content Hashing ──────────────────────────────────────────────────

/**
 * Compute SHA-256 content hash for a PlaybookDocument.
 * Uses canonical JSON serialization for deterministic hashing.
 */
export function computePlaybookContentHash(document: PlaybookDocument): string {
  const canonical = JSON.stringify(deepSortKeys(document), undefined, 0);
  return createHash("sha256").update(canonical).digest("hex");
}

// ─── Validation Helper ────────────────────────────────────────────────

/**
 * Validate a PlaybookDocument and return structured validation results.
 */
export function validatePlaybookDocument(document: PlaybookDocument): PlaybookValidationResult {
  const errors: PlaybookValidationErrorCode[] = [];

  if (document.apiVersion !== PLAYBOOK_API_VERSION) {
    errors.push({
      path: "apiVersion",
      message: `Invalid apiVersion "${document.apiVersion}". Expected "${PLAYBOOK_API_VERSION}"`,
      severity: "error",
      suggestion: `Set apiVersion to "${PLAYBOOK_API_VERSION}"`,
    });
  }

  if (document.kind !== PLAYBOOK_KIND) {
    errors.push({
      path: "kind",
      message: `Invalid kind "${document.kind}". Expected "${PLAYBOOK_KIND}"`,
      severity: "error",
      suggestion: `Set kind to "${PLAYBOOK_KIND}"`,
    });
  }

  if (!document.metadata.id) {
    errors.push({ path: "metadata.id", message: "metadata.id is required", severity: "error" });
  }
  if (!document.metadata.name) {
    errors.push({ path: "metadata.name", message: "metadata.name is required", severity: "error" });
  }
  if (!document.metadata.industry) {
    errors.push({ path: "metadata.industry", message: "metadata.industry is required", severity: "error" });
  }

  if (!document.capabilities || document.capabilities.length === 0) {
    errors.push({
      path: "capabilities",
      message: "Playbook must have at least one capability",
      severity: "error",
      suggestion: "Add at least one capability with id, name, and description",
    });
  }

  document.capabilities?.forEach((cap, i) => {
    if (!cap.id) {
      errors.push({ path: `capabilities[${i}].id`, message: "Capability id is required", severity: "error" });
    }
    if (!cap.name) {
      errors.push({ path: `capabilities[${i}].name`, message: "Capability name is required", severity: "error" });
    }
    if (!cap.description) {
      errors.push({ path: `capabilities[${i}].description`, message: "Capability description is required", severity: "warning" });
    }
  });

  const tierNames = document.pricing.tiers.map((t) => t.name);
  if (!tierNames.includes(PricingTierNameEnum.STARTER as string)) {
    errors.push({ path: "pricing.tiers", message: "Pricing must include a 'starter' tier", severity: "error" });
  }
  if (!tierNames.includes(PricingTierNameEnum.BUSINESS as string)) {
    errors.push({ path: "pricing.tiers", message: "Pricing must include a 'business' tier", severity: "error" });
  }

  if (!document.roi.baseline) {
    errors.push({ path: "roi.baseline", message: "ROI baseline is required", severity: "error" });
  }
  if (!document.roi.projected) {
    errors.push({ path: "roi.projected", message: "ROI projected is required", severity: "error" });
  }

  document.onboarding.steps.forEach((step, i) => {
    if (!step.id) {
      errors.push({ path: `onboarding.steps[${i}].id`, message: "Step id is required", severity: "warning" });
    }
    if (!step.title) {
      errors.push({ path: `onboarding.steps[${i}].title`, message: "Step title is required", severity: "warning" });
    }
  });

  if (document.certification.status === CertificationStatusEnum.UNSIGNED) {
    errors.push({
      path: "certification.status",
      message: "Playbook is not certified — consider requesting certification for production use",
      severity: "warning",
      suggestion: "Submit a CertificationRequest to sign this playbook",
    });
  }

  const errorCount = errors.filter((e) => e.severity === "error").length;
  const warningCount = errors.filter((e) => e.severity === "warning").length;

  return { valid: errorCount === 0, errors, errorCount, warningCount };
}

// ─── YAML Serialization ──────────────────────────────────────────────

/**
 * Serialize a PlaybookDocument back to YAML.
 * Supports round-trip: loadPlaybookFromYaml(documentToYaml(doc)) ≈ doc
 */
export function documentToYaml(document: PlaybookDocument): string {
  const raw = {
    apiVersion: document.apiVersion,
    kind: document.kind,
    metadata: {
      id: document.metadata.id,
      name: document.metadata.name,
      name_en: document.metadata.name_en,
      industry: document.metadata.industry,
      sub_industry: document.metadata.sub_industry,
      compliance: document.metadata.compliance,
      icon: document.metadata.icon,
      color: document.metadata.color,
      version: document.metadata.version,
      description: document.metadata.description,
      author: document.metadata.author,
      ...(Object.keys(document.metadata.labels).length > 0
        ? { labels: document.metadata.labels }
        : {}),
    },
    capabilities: document.capabilities.map((c) => ({
      id: c.id, name: c.name, description: c.description,
      category: c.category, autoEnabled: c.autoEnabled, riskLevel: c.riskLevel,
    })),
    ...(document.policies.length > 0
      ? {
          policies: document.policies.map((p) => ({
            policyId: p.policyId,
            ...(p.reason ? { reason: p.reason } : {}),
            required: p.required,
          })),
        }
      : {}),
    roi: {
      baseline: document.roi.baseline,
      projected: document.roi.projected,
      ...(document.roi.assumptions.length > 0 ? { assumptions: document.roi.assumptions } : {}),
      ...(document.roi.calculated ? { calculated: document.roi.calculated } : {}),
    },
    pricing: {
      currency: document.pricing.currency,
      network: document.pricing.network ?? "TRC20",
      tiers: document.pricing.tiers.map((t) => ({
        name: t.name, price_usdt: t.price_usdt, setup_fee_usdt: t.setup_fee_usdt,
        features: t.features, limits: t.limits, recommended_for: t.recommended_for,
        payment_currency: t.payment_currency, payment_network: t.payment_network,
      })),
    },
    onboarding: {
      steps: document.onboarding.steps.map((s) => ({
        id: s.id, title: s.title, description: s.description,
        type: s.type, field: s.field,
        ...(s.options ? { options: s.options } : {}),
        default_value: s.default_value, required: s.required,
      })),
      estimated_minutes: document.onboarding.estimated_minutes,
    },
    certification: {
      status: document.certification.status,
      ...(document.certification.signedBy ? { signedBy: document.certification.signedBy } : {}),
      ...(document.certification.signedAt ? { signedAt: document.certification.signedAt } : {}),
      ...(document.certification.signature ? { signature: document.certification.signature } : {}),
      ...(document.certification.contentHash ? { contentHash: document.certification.contentHash } : {}),
    },
  };

  return yaml.dump(raw, {
    indent: 2,
    lineWidth: 120,
    noRefs: true,
    sortKeys: true,
    quotingType: '"',
  });
}
