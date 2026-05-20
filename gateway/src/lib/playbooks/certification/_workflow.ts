// ─── Zenic-Agents v3 — Certification Workflow & Utilities ────────────
// Fingerprint generation, document reconstruction, canonicalization,
// and certification status retrieval.
//
// Design Patterns:
//   - Strategy: fingerprint generation excludes certification fields
//   - Verification: verifyCertification recomputes and compares

import { createHash } from "crypto";
import { db } from "@/lib/db";
import type {
  PlaybookDocument,
  PlaybookMetadata,
  PlaybookCapability,
  PolicyReference,
  PlaybookRoiConfig,
  PlaybookPricing,
  PlaybookOnboardingConfig,
  CertificationStatus,
} from "../types";
import { CertificationStatus as CertificationStatusEnum } from "../types";
import type { CertificationStatusInfo } from "./types";

// ─── Fingerprint Generation ──────────────────────────────────────────

/**
 * Generate a deterministic SHA-256 fingerprint of a PlaybookDocument.
 * Uses canonical JSON to ensure consistent hashing.
 * Includes: metadata, capabilities, policies, roiConfig, pricing, onboarding.
 * Excludes: certification fields (to avoid circular dependency).
 */
export function generatePlaybookFingerprint(doc: PlaybookDocument): string {
  // Build a canonical object excluding certification fields
  const canonical = {
    apiVersion: doc.apiVersion,
    kind: doc.kind,
    metadata: canonicalizeMetadata(doc.metadata),
    capabilities: doc.capabilities.map(canonicalizeCapability),
    policies: doc.policies.map(canonicalizePolicy),
    roi: doc.roi,
    pricing: doc.pricing,
    onboarding: doc.onboarding,
  };

  // Sort object keys recursively for deterministic serialization
  const canonicalJson = JSON.stringify(canonical, Object.keys(canonical).sort());

  return createHash("sha256").update(canonicalJson).digest("hex");
}

// ─── Certification Status ────────────────────────────────────────────

/**
 * Get the certification status information for a playbook.
 */
export async function getCertificationStatus(
  playbookId: string,
): Promise<CertificationStatusInfo> {
  try {
    const playbook = await db.playbook.findFirst({
      where: { playbookId },
    });

    if (!playbook) {
      return {
        playbookId,
        status: CertificationStatusEnum.UNSIGNED,
        hashIntact: false,
        description: `Playbook "${playbookId}" not found`,
      };
    }

    // Check if the current content hash matches the certified hash
    let hashIntact = false;
    if (playbook.certificationHash && playbook.certificationStatus === CertificationStatusEnum.CERTIFIED) {
      const document = reconstructDocument(playbook);
      const currentHash = generatePlaybookFingerprint(document);
      hashIntact = currentHash === playbook.certificationHash;
    }

    const description = getCertificationDescription(
      playbook.certificationStatus as CertificationStatus,
      hashIntact,
    );

    return {
      playbookId,
      status: playbook.certificationStatus as CertificationStatus,
      signedBy: playbook.certificationSignedBy ?? undefined,
      signedAt: playbook.certificationSignedAt?.toISOString() ?? undefined,
      contentHash: playbook.certificationHash ?? undefined,
      hashIntact,
      description,
    };
  } catch (error) {
    return {
      playbookId,
      status: CertificationStatusEnum.UNSIGNED,
      hashIntact: false,
      description: `Error retrieving status: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

// ─── Internal Helpers ────────────────────────────────────────────────

/**
 * Reconstruct a PlaybookDocument from a DB record.
 * Excludes certification fields (they are set separately).
 */
export function reconstructDocument(p: {
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
  author: string | null;
}): PlaybookDocument {
  return {
    apiVersion: p.apiVersion as PlaybookDocument["apiVersion"],
    kind: "Playbook" as const,
    metadata: {
      id: p.playbookId,
      name: p.name,
      name_en: p.nameEn ?? p.name,
      industry: p.industry as PlaybookMetadata["industry"],
      sub_industry: p.subIndustry ?? "",
      compliance: JSON.parse(p.compliance),
      icon: p.icon ?? "",
      color: p.color ?? "#6b7280",
      version: p.version,
      description: p.description,
      author: p.author ?? "system",
      labels: JSON.parse(p.labels),
    },
    capabilities: JSON.parse(p.capabilities) as PlaybookCapability[],
    policies: JSON.parse(p.policies) as PolicyReference[],
    roi: JSON.parse(p.roiConfig) as PlaybookRoiConfig,
    pricing: JSON.parse(p.pricing) as PlaybookPricing,
    onboarding: JSON.parse(p.onboarding) as PlaybookOnboardingConfig,
    // Certification excluded from fingerprint — use default unsigned
    certification: {
      status: CertificationStatusEnum.UNSIGNED,
    },
  };
}

/**
 * Canonicalize metadata for deterministic fingerprinting.
 */
function canonicalizeMetadata(metadata: PlaybookMetadata): Record<string, unknown> {
  return {
    id: metadata.id,
    name: metadata.name,
    name_en: metadata.name_en,
    industry: metadata.industry,
    sub_industry: metadata.sub_industry,
    compliance: [...metadata.compliance].sort(),
    icon: metadata.icon,
    color: metadata.color,
    version: metadata.version,
    description: metadata.description,
    author: metadata.author,
    labels: metadata.labels,
  };
}

/**
 * Canonicalize a capability for deterministic fingerprinting.
 */
function canonicalizeCapability(cap: PlaybookCapability): Record<string, unknown> {
  return {
    id: cap.id,
    name: cap.name,
    description: cap.description,
    category: cap.category,
    autoEnabled: cap.autoEnabled,
    riskLevel: cap.riskLevel,
  };
}

/**
 * Canonicalize a policy reference for deterministic fingerprinting.
 */
function canonicalizePolicy(policy: PolicyReference): Record<string, unknown> {
  return {
    policyId: policy.policyId,
    reason: policy.reason ?? "",
    required: policy.required,
  };
}

/**
 * Get a human-readable description for a certification status.
 */
export function getCertificationDescription(
  status: CertificationStatus,
  hashIntact: boolean,
): string {
  switch (status) {
    case CertificationStatusEnum.CERTIFIED:
      if (hashIntact) {
        return "Playbook is certified and content has not been modified since certification";
      }
      return "Playbook is certified but content has been modified — re-certification recommended";
    case CertificationStatusEnum.PENDING:
      return "Certification request is pending review";
    case CertificationStatusEnum.REVOKED:
      return "Certification has been revoked — a new version must be submitted for re-certification";
    case CertificationStatusEnum.UNSIGNED:
    default:
      return "Playbook has not been certified — request certification for production use";
  }
}
