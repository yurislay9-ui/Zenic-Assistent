// ─── Zenic-Agents v3 — Playbook YAML Loader: Transformer ──────────────
// Content hashing and YAML serialization (round-trip support).

import yaml from "js-yaml";
import { createHash } from "crypto";

import type { PlaybookDocument } from "../types";

// ─── Content Hashing ──────────────────────────────────────────────────

/**
 * Compute SHA-256 content hash for a PlaybookDocument.
 * Uses canonical JSON serialization for deterministic hashing.
 */
export function computePlaybookContentHash(document: PlaybookDocument): string {
  // Deep-sort all keys recursively for deterministic hashing
  const canonical = JSON.stringify(deepSortKeys(document), undefined, 0);
  return createHash("sha256").update(canonical).digest("hex");
}

/** Recursively sort object keys for deterministic serialization */
function deepSortKeys(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) return obj.map(deepSortKeys);
  if (typeof obj === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(obj as Record<string, unknown>).sort()) {
      sorted[key] = deepSortKeys((obj as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return obj;
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
      id: c.id,
      name: c.name,
      description: c.description,
      category: c.category,
      autoEnabled: c.autoEnabled,
      riskLevel: c.riskLevel,
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
      ...(document.roi.assumptions.length > 0
        ? { assumptions: document.roi.assumptions }
        : {}),
      ...(document.roi.calculated ? { calculated: document.roi.calculated } : {}),
    },
    pricing: {
      currency: document.pricing.currency,
      network: document.pricing.network ?? "TRC20",
      tiers: document.pricing.tiers.map((t) => ({
        name: t.name,
        price_usdt: t.price_usdt,
        setup_fee_usdt: t.setup_fee_usdt,
        features: t.features,
        limits: t.limits,
        recommended_for: t.recommended_for,
        payment_currency: t.payment_currency,
        payment_network: t.payment_network,
      })),
    },
    onboarding: {
      steps: document.onboarding.steps.map((s) => ({
        id: s.id,
        title: s.title,
        description: s.description,
        type: s.type,
        field: s.field,
        ...(s.options ? { options: s.options } : {}),
        default_value: s.default_value,
        required: s.required,
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
