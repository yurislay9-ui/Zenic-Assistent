// ─── Zenic-Agents v3 — Playbook YAML Loader: Validator ─────────────────
// Post-compilation validation that returns structured results instead of
// throwing errors.

import {
  PLAYBOOK_API_VERSION,
  PLAYBOOK_KIND,
  CertificationStatus,
  PricingTierName,
  type PlaybookDocument,
  type PlaybookValidationError as PlaybookValidationErrorCode,
  type PlaybookValidationResult,
} from "../types";

// ─── Validation Helper ────────────────────────────────────────────────

/**
 * Validate a PlaybookDocument and return structured validation results.
 */
export function validatePlaybookDocument(document: PlaybookDocument): PlaybookValidationResult {
  const errors: PlaybookValidationErrorCode[] = [];

  // Validate apiVersion
  if (document.apiVersion !== PLAYBOOK_API_VERSION) {
    errors.push({
      path: "apiVersion",
      message: `Invalid apiVersion "${document.apiVersion}". Expected "${PLAYBOOK_API_VERSION}"`,
      severity: "error",
      suggestion: `Set apiVersion to "${PLAYBOOK_API_VERSION}"`,
    });
  }

  // Validate kind
  if (document.kind !== PLAYBOOK_KIND) {
    errors.push({
      path: "kind",
      message: `Invalid kind "${document.kind}". Expected "${PLAYBOOK_KIND}"`,
      severity: "error",
      suggestion: `Set kind to "${PLAYBOOK_KIND}"`,
    });
  }

  // Validate metadata
  if (!document.metadata.id) {
    errors.push({
      path: "metadata.id",
      message: "metadata.id is required",
      severity: "error",
    });
  }
  if (!document.metadata.name) {
    errors.push({
      path: "metadata.name",
      message: "metadata.name is required",
      severity: "error",
    });
  }
  if (!document.metadata.industry) {
    errors.push({
      path: "metadata.industry",
      message: "metadata.industry is required",
      severity: "error",
    });
  }

  // Validate capabilities
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

  // Validate pricing tiers
  const tierNames = document.pricing.tiers.map((t) => t.name);
  if (!tierNames.includes(PricingTierName.STARTER)) {
    errors.push({
      path: "pricing.tiers",
      message: "Pricing must include a 'starter' tier",
      severity: "error",
    });
  }
  if (!tierNames.includes(PricingTierName.BUSINESS)) {
    errors.push({
      path: "pricing.tiers",
      message: "Pricing must include a 'business' tier",
      severity: "error",
    });
  }

  // Validate ROI config
  if (!document.roi.baseline) {
    errors.push({
      path: "roi.baseline",
      message: "ROI baseline is required",
      severity: "error",
    });
  }
  if (!document.roi.projected) {
    errors.push({
      path: "roi.projected",
      message: "ROI projected is required",
      severity: "error",
    });
  }

  // Validate onboarding steps
  document.onboarding.steps.forEach((step, i) => {
    if (!step.id) {
      errors.push({ path: `onboarding.steps[${i}].id`, message: "Step id is required", severity: "warning" });
    }
    if (!step.title) {
      errors.push({ path: `onboarding.steps[${i}].title`, message: "Step title is required", severity: "warning" });
    }
  });

  // Certification warning for unsigned playbooks
  if (document.certification.status === CertificationStatus.UNSIGNED) {
    errors.push({
      path: "certification.status",
      message: "Playbook is not certified — consider requesting certification for production use",
      severity: "warning",
      suggestion: "Submit a CertificationRequest to sign this playbook",
    });
  }

  const errorCount = errors.filter((e) => e.severity === "error").length;
  const warningCount = errors.filter((e) => e.severity === "warning").length;

  return {
    valid: errorCount === 0,
    errors,
    errorCount,
    warningCount,
  };
}
