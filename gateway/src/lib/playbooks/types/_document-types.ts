// ─── Zenic-Agents v3 — Playbook Document Types ──────────────────────────
// Split from types.ts — core document structure, metadata, capabilities, policies

import type { Industry, CapabilityCategory, CapabilityRiskLevel, CertificationStatus } from "./_enums";
import { PLAYBOOK_API_VERSION, PLAYBOOK_KIND } from "./_enums";
import type { PlaybookRoiConfig } from "./_roi-types";
import type { PlaybookPricing } from "./_pricing-types";
import type { PlaybookOnboardingConfig } from "./_onboarding-types";

/** Playbook metadata — identifies and categorizes the playbook */
export interface PlaybookMetadata {
  /** Unique playbook identifier (e.g., "financial-control-v1") */
  id: string;
  /** Human-readable name in Spanish (e.g., "Control Financiero Automatizado") */
  name: string;
  /** Human-readable name in English (e.g., "Automated Financial Control") */
  name_en: string;
  /** Primary industry this playbook targets */
  industry: Industry;
  /** Specific sub-industry niche (e.g., "banking", "fintech", "crypto") */
  sub_industry: string;
  /** Compliance standards this playbook satisfies */
  compliance: string[];
  /** Emoji or icon identifier for UI display */
  icon: string;
  /** Brand color (hex) for UI theming */
  color: string;
  /** Semantic version (semver) */
  version: string;
  /** Description of what this playbook delivers */
  description: string;
  /** Author of the playbook */
  author: string;
  /** Labels for categorization, filtering, and search */
  labels: Record<string, string>;
}

/** A single capability provided by a playbook */
export interface PlaybookCapability {
  /** Unique capability identifier (e.g., "auto-reconciliation") */
  id: string;
  /** Human-readable name */
  name: string;
  /** What this capability does */
  description: string;
  /** Category for grouping */
  category: CapabilityCategory;
  /** Whether this capability is enabled by default on activation */
  autoEnabled: boolean;
  /** Risk level — high/critical capabilities require explicit approval */
  riskLevel: CapabilityRiskLevel;
}

/** Reference to a DeclPolicy from Phase 3 Policy Engine */
export interface PolicyReference {
  /** Policy ID matching DeclPolicy.id in the policy engine */
  policyId: string;
  /** Human-readable description of why this policy is included */
  reason?: string;
  /** Whether this policy is required or optional for the playbook */
  required: boolean;
}

/** Cryptographic certification embedded in the playbook document */
export interface PlaybookCertification {
  /** Current certification status */
  status: CertificationStatus;
  /** Identity of the certifying authority */
  signedBy?: string;
  /** Timestamp when the certification was signed (ISO 8601) */
  signedAt?: string;
  /** Cryptographic signature (e.g., RSA/ECDSA hex) */
  signature?: string;
  /** SHA-256 content hash of the canonical playbook document */
  contentHash?: string;
}

/** Request to certify a playbook */
export interface CertificationRequest {
  /** Playbook ID to certify */
  playbookId: string;
  /** Identity of the person or system requesting certification */
  requestedBy: string;
  /** Business justification for certification */
  justification: string;
}

/** Result of a certification attempt */
export interface CertificationResult {
  /** Whether the certification succeeded */
  success: boolean;
  /** The cryptographic signature (if successful) */
  signature?: string;
  /** The SHA-256 content hash of the certified document */
  hash?: string;
  /** Timestamp when the certification was verified (ISO 8601) */
  verifiedAt?: string;
  /** Error message if certification failed */
  error?: string;
}

/** The full declarative playbook document — YAML-native format */
export interface PlaybookDocument {
  /** API version — always "playbook.zenic.dev/v1" */
  apiVersion: typeof PLAYBOOK_API_VERSION;
  /** Document kind — always "Playbook" */
  kind: typeof PLAYBOOK_KIND;
  /** Playbook identification and classification */
  metadata: PlaybookMetadata;
  /** Capabilities this playbook provides */
  capabilities: PlaybookCapability[];
  /** References to policies from the Policy Engine (Phase 3) */
  policies: PolicyReference[];
  /** ROI configuration with baseline, projections, and formulas */
  roi: PlaybookRoiConfig;
  /** Pricing tiers and feature matrix */
  pricing: PlaybookPricing;
  /** Onboarding configuration with guided setup steps */
  onboarding: PlaybookOnboardingConfig;
  /** Cryptographic certification status */
  certification: PlaybookCertification;
}
