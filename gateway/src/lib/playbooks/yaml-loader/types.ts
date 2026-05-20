// ─── Zenic-Agents v3 — Playbook YAML Loader: Types & Constants ──────────
// Error classes, loader configuration, and validation constant sets.
// Shared across all yaml-loader sub-modules.

import {
  CertificationStatus,
  PricingTierName,
} from "../types";

// ─── Validation Errors ────────────────────────────────────────────────

export class PlaybookValidationError extends Error {
  constructor(
    message: string,
    public readonly field: string,
    public readonly value?: unknown,
  ) {
    super(`Playbook validation error at "${field}": ${message}`);
    this.name = "PlaybookValidationError";
  }
}

export class PlaybookCompilationError extends Error {
  constructor(
    message: string,
    public readonly playbookId?: string,
  ) {
    super(`Playbook compilation error${playbookId ? ` for "${playbookId}"` : ""}: ${message}`);
    this.name = "PlaybookCompilationError";
  }
}

// ─── Loader Configuration ─────────────────────────────────────────────

export interface PlaybookYamlLoaderConfig {
  /** Whether to validate on load */
  strictValidation: boolean;
  /** Whether to allow unknown fields */
  allowUnknownFields: boolean;
  /** Whether to compute content hash */
  computeHash: boolean;
  /** Default author if not specified */
  defaultAuthor: string;
}

export const DEFAULT_LOADER_CONFIG: PlaybookYamlLoaderConfig = {
  strictValidation: true,
  allowUnknownFields: false,
  computeHash: true,
  defaultAuthor: "system",
};

// ─── Valid Constants ──────────────────────────────────────────────────

export const VALID_INDUSTRIES: ReadonlySet<string> = new Set<string>([
  "financial_services", "healthcare", "insurance", "real_estate",
  "legal", "ecommerce", "logistics", "manufacturing",
  "energy", "telecommunications", "government", "education",
  "agriculture", "hospitality", "retail", "construction",
  "automotive", "pharmaceutical", "media", "nonprofit",
  "technology", "consulting", "food_beverage", "mining",
]);

export const VALID_CAPABILITY_CATEGORIES: ReadonlySet<string> = new Set<string>([
  "automation", "compliance", "security", "analytics",
  "integration", "workflow", "reporting", "monitoring",
]);

export const VALID_RISK_LEVELS: ReadonlySet<string> = new Set<string>([
  "low", "medium", "high", "critical",
]);

export const VALID_STEP_TYPES: ReadonlySet<string> = new Set<string>([
  "question", "selection", "confirmation", "auto_config",
]);

export const VALID_TIER_NAMES: ReadonlySet<string> = new Set<string>([
  "starter", "business", "enterprise", "on_premise_enterprise", "trial",
]);

export const VALID_CERTIFICATION_STATUSES: ReadonlySet<string> = new Set<string>([
  "unsigned", "pending", "certified", "revoked",
]);
