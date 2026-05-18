// ─── Zenic-Agents v3 — Playbook YAML Loader: Parser ────────────────────
// YAML parsing and top-level document compilation orchestrator.

import yaml from "js-yaml";

import {
  PLAYBOOK_API_VERSION,
  PLAYBOOK_KIND,
  type PlaybookDocument,
} from "../types";

import {
  PlaybookValidationError,
  PlaybookCompilationError,
  DEFAULT_LOADER_CONFIG,
  type PlaybookYamlLoaderConfig,
} from "./types";

import {
  compileMetadata,
  compileCapability,
  compilePolicyReference,
} from "./_compiler-core";

import {
  compileRoiConfig,
} from "./_compiler-roi";

import {
  compilePricing,
  compileOnboarding,
  compileCertification,
} from "./_compiler-struct";

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

  // 1. Parse YAML
  let raw: unknown;
  try {
    raw = yaml.load(yamlContent);
  } catch (err) {
    throw new PlaybookCompilationError(
      `YAML parse error: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  // 2. Validate and compile
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

  // Validate apiVersion
  if (obj.apiVersion !== PLAYBOOK_API_VERSION) {
    if (config.strictValidation) {
      throw new PlaybookValidationError(
        `Invalid apiVersion "${String(obj.apiVersion)}". Expected "${PLAYBOOK_API_VERSION}"`,
        "apiVersion",
        obj.apiVersion,
      );
    }
  }

  // Validate kind
  if (obj.kind !== PLAYBOOK_KIND) {
    if (config.strictValidation) {
      throw new PlaybookValidationError(
        `Invalid kind "${String(obj.kind)}". Expected "${PLAYBOOK_KIND}"`,
        "kind",
        obj.kind,
      );
    }
  }

  // Validate metadata
  const metadata = compileMetadata(obj.metadata, config);

  // Validate capabilities
  if (!Array.isArray(obj.capabilities) || obj.capabilities.length === 0) {
    throw new PlaybookValidationError(
      "Playbook must have at least one capability",
      "capabilities",
    );
  }
  const capabilities = obj.capabilities.map((c: unknown, i: number) =>
    compileCapability(c, i, config),
  );

  // Validate policies (optional, can be empty)
  const policies = Array.isArray(obj.policies)
    ? obj.policies.map((p: unknown, i: number) => compilePolicyReference(p, i, config))
    : [];

  // Validate ROI config
  const roi = compileRoiConfig(obj.roi, config);

  // Validate pricing
  const pricing = compilePricing(obj.pricing, config);

  // Validate onboarding
  const onboarding = compileOnboarding(obj.onboarding, config);

  // Validate certification (optional, defaults to unsigned)
  const certification = compileCertification(obj.certification, config);

  const doc: PlaybookDocument = {
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

  return doc;
}
