// ─── Zenic-Agents v3 — Playbook Engine (core motor) ──────────────────────
// CRUD operations, evaluation, and activation for industry playbooks.
// Singleton pattern matching policy-engine/evaluator.ts.
// Lazy imports for cross-module dependencies (roi-calculator, pricing-engine).
//
// Design Patterns:
//   - Singleton: single PlaybookEngine instance for the running service
//   - Strategy: evaluation scoring varies by industry
//   - Repository: DB access through Prisma abstraction

import { db } from "@/lib/db";
import type {
  PlaybookDocument,
  PlaybookMetadata,
  PlaybookCapability,
  PolicyReference,
  PlaybookRoiConfig,
  RoiBaseline,
  RoiProjected,
  RoiCalculation,
  PlaybookPricing,
  PricingTier,
  PricingTierName,
  PlaybookOnboardingConfig,
  PlaybookCertification,
  PlaybookEvaluationResult,
  PlaybookActivationRequest,
  PlaybookActivationResult,
  PlaybookSearchCriteria,
  PlaybookSearchResult,
  PlaybookEngineConfig,
  Industry,
  CertificationStatus,
  PlaybookStatus,
} from "./types";
import {
  DEFAULT_PLAYBOOK_ENGINE_CONFIG,
  PricingTierName as PricingTierNameEnum,
  CertificationStatus as CertificationStatusEnum,
  PlaybookStatus as PlaybookStatusEnum,
} from "./types";
import { computePlaybookContentHash, PlaybookCompilationError } from "./yaml-loader";

// ─── Lazy Import Types ────────────────────────────────────────────────
// Cross-module dependencies loaded lazily to avoid circular imports

type RoiCalculatorModule = {
  calculateRoi: (input: {
    baseline: RoiBaseline;
    projected: RoiProjected;
    monthlyCostUsd: number;
    workingHoursPerMonth?: number;
    hourlyCostUsd?: number;
  }) => RoiCalculation;
};

type PricingEngineModule = {
  calculatePricing: (input: {
    pricing: PlaybookPricing;
    selectedTier: PricingTierName;
    actionsPerMonth: number;
  }) => {
    selected_tier: PricingTierName;
    monthly_cost_usdt: number;
    annual_cost_usdt: number;
    setup_fee_usdt: number;
    per_action_cost: number;
    break_even_actions: number;
    payment_currency: string;
    payment_network: string;
  };
};

// ─── Playbook Engine ──────────────────────────────────────────────────

export class PlaybookEngine {
  private config: PlaybookEngineConfig;
  private cache: Map<string, { document: PlaybookDocument; expiresAt: number }> = new Map();

  constructor(config?: Partial<PlaybookEngineConfig>) {
    this.config = { ...DEFAULT_PLAYBOOK_ENGINE_CONFIG, ...config };
  }

  // ─── CRUD Operations ──────────────────────────────────────────────

  /**
   * Create a new playbook from a compiled PlaybookDocument.
   * Stores the document in the database with content hash.
   */
  async createPlaybook(
    doc: PlaybookDocument,
    sourceYaml?: string,
  ): Promise<PlaybookDbRecord> {
    try {
      const contentHash = computePlaybookContentHash(doc);

      // Check for duplicate content hash
      const existing = await db.playbook.findFirst({
        where: { contentHash },
      });

      if (existing) {
        throw new PlaybookCompilationError(
          `Playbook with identical content already exists (id: ${existing.playbookId})`,
          doc.metadata.id,
        );
      }

      // Check for duplicate playbook ID
      const existingById = await db.playbook.findFirst({
        where: { playbookId: doc.metadata.id },
      });

      if (existingById) {
        throw new PlaybookCompilationError(
          `Playbook with id "${doc.metadata.id}" already exists`,
          doc.metadata.id,
        );
      }

      const playbook = await db.playbook.create({
        data: {
          playbookId: doc.metadata.id,
          name: doc.metadata.name,
          nameEn: doc.metadata.name_en,
          industry: doc.metadata.industry,
          subIndustry: doc.metadata.sub_industry,
          apiVersion: doc.apiVersion,
          version: doc.metadata.version,
          description: doc.metadata.description,
          icon: doc.metadata.icon,
          color: doc.metadata.color,
          labels: JSON.stringify(doc.metadata.labels),
          compliance: JSON.stringify(doc.metadata.compliance),
          capabilities: JSON.stringify(doc.capabilities),
          policies: JSON.stringify(doc.policies),
          roiConfig: JSON.stringify(doc.roi),
          pricing: JSON.stringify(doc.pricing),
          onboarding: JSON.stringify(doc.onboarding),
          certificationStatus: doc.certification.status,
          certificationSignedBy: doc.certification.signedBy,
          certificationSignedAt: doc.certification.signedAt ? new Date(doc.certification.signedAt) : null,
          certificationSignature: doc.certification.signature,
          certificationHash: doc.certification.contentHash,
          sourceYaml: sourceYaml ?? null,
          contentHash,
          isActive: true,
          author: doc.metadata.author,
        },
      });
