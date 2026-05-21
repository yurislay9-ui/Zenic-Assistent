// ─── Zenic-Agents v3 — YAML Policy Parser ──────────────────────────────
// Parses YAML content into PolicyDocument objects and serializes back.
// Uses js-yaml for parsing; delegates validation to _validator.

import yaml from "js-yaml";
import { createHash } from "crypto";
import type { PolicyDocument } from "../types";
import {
  type YamlLoaderConfig,
  DEFAULT_LOADER_CONFIG,
  PolicyCompilationError,
  compilePolicyDocument,
} from "./_validator";

// ─── Core Loader Function ────────────────────────────────────────────

/**
 * Parse a YAML string into a PolicyDocument.
 * Validates structure and semantics.
 */
export function loadPolicyFromYaml(
  yamlContent: string,
  config: Partial<YamlLoaderConfig> = {},
): PolicyDocument {
  const cfg = { ...DEFAULT_LOADER_CONFIG, ...config };

  // 1. Parse YAML
  let raw: unknown;
  try {
    raw = yaml.load(yamlContent, { schema: yaml.DEFAULT_SAFE_SCHEMA });
  } catch (err) {
    throw new PolicyCompilationError(
      `YAML parse error: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  // 2. Validate and compile
  return compilePolicyDocument(raw, cfg);
}

// ─── Content Hashing ──────────────────────────────────────────────────

/**
 * Compute SHA-256 content hash for a PolicyDocument.
 * Uses canonical JSON serialization for deterministic hashing.
 */
export function computeContentHash(document: PolicyDocument): string {
  const canonical = JSON.stringify(document, Object.keys(document).sort(), 2);
  return createHash("sha256").update(canonical).digest("hex");
}

// ─── YAML Serialization ──────────────────────────────────────────────

/**
 * Serialize a PolicyDocument back to YAML.
 */
export function documentToYaml(document: PolicyDocument): string {
  const raw = {
    apiVersion: document.apiVersion,
    kind: document.kind,
    metadata: {
      id: document.metadata.id,
      name: document.metadata.name,
      version: document.metadata.version,
      description: document.metadata.description,
      ...(document.metadata.compliance ? {
        compliance: document.metadata.compliance.reduce(
          (acc, c) => ({ ...acc, [c.standard]: c.sections.join(", ") }),
          {} as Record<string, string>,
        ),
      } : {}),
      ...(document.metadata.labels ? { labels: document.metadata.labels } : {}),
      ...(document.metadata.author ? { author: document.metadata.author } : {}),
    },
    statements: document.statements.map((s) => ({
      id: s.id,
      effect: s.effect,
      resource: s.resource,
      action: s.action,
      ...(s.conditions ? { conditions: s.conditions.map((c) => ({
        field: c.field,
        operator: c.operator,
        value: c.value,
        ...(c.description ? { description: c.description } : {}),
      }))} : {}),
      priority: s.priority,
      ...(s.description ? { description: s.description } : {}),
      ...(s.requiredRole ? { requiredRole: s.requiredRole } : {}),
      ...(s.tags ? { tags: s.tags } : {}),
    })),
    ...(document.tests ? {
      tests: document.tests.map((t) => ({
        name: t.name,
        resource: t.resource,
        action: t.action,
        context: t.context,
        expected: t.expected,
        ...(t.expectedStatementId ? { expectedStatementId: t.expectedStatementId } : {}),
      })),
    } : {}),
  };

  return yaml.dump(raw, {
    indent: 2,
    lineWidth: 120,
    noRefs: true,
    sortKeys: true,
    quotingType: '"',
  });
}
