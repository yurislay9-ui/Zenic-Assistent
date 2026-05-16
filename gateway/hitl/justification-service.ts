// ─── Zenic-Agents v3 — HITL Justification Service ─────────────────────
// Phase 5: Mandatory justification for approve/reject decisions
//
// Design Patterns:
//   - Singleton: Single service instance via getJustificationService()
//   - Strategy: Priority-based validation rules
//   - Value Object: Immutable justification records with SHA-256 hash
//   - Observer: Records audit events when justifications are provided

import { createHash } from "crypto";
import { db } from "@/lib/db";
import {
  type ApprovalJustification,
  type ProvideJustificationInput,
  type ApprovalPriority,
  ApprovalPriority as ApprovalPriorityEnum,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "./approval-audit";

// ═══════════════════════════════════════════════════════════════════════════
// ID Generation
// ═══════════════════════════════════════════════════════════════════════════

function generateJustificationId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `just_${timestamp}_${random}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Content Hashing
// ═══════════════════════════════════════════════════════════════════════════

/** Compute SHA-256 content hash for justification immutability */
function computeJustificationHash(data: {
  requestId: string;
  decisionId: string | null;
  reason: string;
  riskAcknowledgment: boolean;
  complianceCheck: boolean;
  businessJustification: string;
  createdBy: string;
  createdByName: string;
  timestamp: string;
}): string {
  const canonical = JSON.stringify({
    requestId: data.requestId,
    decisionId: data.decisionId,
    reason: data.reason,
    riskAcknowledgment: data.riskAcknowledgment,
    complianceCheck: data.complianceCheck,
    businessJustification: data.businessJustification,
    createdBy: data.createdBy,
    createdByName: data.createdByName,
    timestamp: data.timestamp,
  });
  return createHash("sha256").update(canonical).digest("hex");
}

// ═══════════════════════════════════════════════════════════════════════════
// Priority-Based Validation Rules
// ═══════════════════════════════════════════════════════════════════════════

interface JustificationValidationRule {
  /** Minimum reason length */
  minReasonLength: number;
  /** Whether risk acknowledgment is required */
  requireRiskAcknowledgment: boolean;
  /** Whether compliance check is required */
  requireComplianceCheck: boolean;
  /** Whether business justification is required */
  requireBusinessJustification: boolean;
}

const VALIDATION_RULES: Record<string, JustificationValidationRule> = {
  [ApprovalPriorityEnum.CRITICAL]: {
    minReasonLength: 50,
    requireRiskAcknowledgment: true,
    requireComplianceCheck: true,
    requireBusinessJustification: true,
  },
  [ApprovalPriorityEnum.EMERGENCY]: {
    minReasonLength: 50,
    requireRiskAcknowledgment: true,
    requireComplianceCheck: true,
    requireBusinessJustification: true,
  },
  [ApprovalPriorityEnum.HIGH]: {
    minReasonLength: 30,
    requireRiskAcknowledgment: true,
    requireComplianceCheck: true,
    requireBusinessJustification: false,
  },
  [ApprovalPriorityEnum.MEDIUM]: {
    minReasonLength: 20,
    requireRiskAcknowledgment: true,
    requireComplianceCheck: false,
    requireBusinessJustification: false,
  },
  [ApprovalPriorityEnum.LOW]: {
    minReasonLength: 10,
    requireRiskAcknowledgment: false,
    requireComplianceCheck: false,
    requireBusinessJustification: false,
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// Justification Service (Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class JustificationService {
  private static instance: JustificationService | null = null;

  private constructor() {}

  static getInstance(): JustificationService {
    if (!JustificationService.instance) {
      JustificationService.instance = new JustificationService();
    }
    return JustificationService.instance;
  }

  /** Provide a justification for an approval/rejection decision */
  async provideJustification(
    requestId: string,
    input: ProvideJustificationInput,
    priority?: ApprovalPriority,
  ): Promise<ApprovalJustification> {
    // Validate the request exists
    const request = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!request) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    // Use the request's priority if not explicitly provided
    const effectivePriority = priority ?? (request.priority as ApprovalPriority);

    // Validate the justification against priority rules
    const validation = this.validateJustification(input, effectivePriority);
    if (!validation.valid) {
      throw new Error(
        `Justification validation failed: ${validation.errors.join("; ")}`,
      );
    }

    const justificationId = generateJustificationId();
    const timestamp = new Date().toISOString();
    const businessJustification = input.businessJustification ?? "";

    const contentHash = computeJustificationHash({
      requestId,
      decisionId: input.decisionId ?? null,
      reason: input.reason,
      riskAcknowledgment: input.riskAcknowledgment,
      complianceCheck: input.complianceCheck,
      businessJustification,
      createdBy: input.createdBy,
      createdByName: input.createdByName,
      timestamp,
    });

    const record = await db.hitlJustification.create({
      data: {
        justificationId,
        requestId,
        decisionId: input.decisionId ?? null,
        reason: input.reason,
        riskAcknowledgment: input.riskAcknowledgment,
        complianceCheck: input.complianceCheck,
        businessJustification,
        createdBy: input.createdBy,
        createdByName: input.createdByName,
        contentHash,
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: "created" as HitlEventType,
      actorId: input.createdBy,
      actorName: input.createdByName,
      details: {
        action: "justification_provided",
        justificationId,
        decisionId: input.decisionId ?? null,
        riskAcknowledgment: input.riskAcknowledgment,
        complianceCheck: input.complianceCheck,
        contentHash,
      },
    });

    return this.mapRecordToModel(record);
  }

  /** Get the justification for an approval request */
  async getJustification(requestId: string): Promise<ApprovalJustification | null> {
    const record = await db.hitlJustification.findFirst({
      where: { requestId },
      orderBy: { createdAt: "desc" },
    });

    if (!record) return null;
    return this.mapRecordToModel(record);
  }

  /** Validate a justification input against priority-based rules */
  validateJustification(
    input: ProvideJustificationInput,
    priority: ApprovalPriority,
  ): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    const rule = VALIDATION_RULES[priority];

    if (!rule) {
      // Unknown priority — use medium rules
      const fallback = VALIDATION_RULES[ApprovalPriorityEnum.MEDIUM];
      return this.applyValidationRules(input, fallback);
    }

    return this.applyValidationRules(input, rule);
  }

  /** Verify the integrity of a justification record by recomputing its content hash */
  async verifyJustificationIntegrity(justificationId: string): Promise<{
    valid: boolean;
    justificationId: string;
  }> {
    const record = await db.hitlJustification.findUnique({
      where: { justificationId },
    });

    if (!record) {
      throw new Error(`Justification "${justificationId}" not found`);
    }

    const expectedHash = computeJustificationHash({
      requestId: record.requestId,
      decisionId: record.decisionId,
      reason: record.reason,
      riskAcknowledgment: record.riskAcknowledgment,
      complianceCheck: record.complianceCheck,
      businessJustification: record.businessJustification,
      createdBy: record.createdBy,
      createdByName: record.createdByName,
      timestamp: record.createdAt.toISOString(),
    });

    return {
      valid: record.contentHash === expectedHash,
      justificationId: record.justificationId,
    };
  }

  /** Apply validation rules to input */
  private applyValidationRules(
    input: ProvideJustificationInput,
    rule: JustificationValidationRule,
  ): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (input.reason.trim().length < rule.minReasonLength) {
      errors.push(
        `Reason must be at least ${rule.minReasonLength} characters (got ${input.reason.trim().length})`,
      );
    }

    if (rule.requireRiskAcknowledgment && !input.riskAcknowledgment) {
      errors.push("Risk acknowledgment is required for this priority level");
    }

    if (rule.requireComplianceCheck && !input.complianceCheck) {
      errors.push("Compliance check is required for this priority level");
    }

    if (
      rule.requireBusinessJustification &&
      (!input.businessJustification || input.businessJustification.trim().length === 0)
    ) {
      errors.push("Business justification is required for this priority level");
    }

    return { valid: errors.length === 0, errors };
  }

  /** Map a database record to the domain model */
  private mapRecordToModel(record: {
    id: string;
    justificationId: string;
    requestId: string;
    decisionId: string | null;
    reason: string;
    riskAcknowledgment: boolean;
    complianceCheck: boolean;
    businessJustification: string;
    createdBy: string;
    createdByName: string;
    contentHash: string;
    createdAt: Date;
  }): ApprovalJustification {
    return {
      justificationId: record.justificationId,
      requestId: record.requestId,
      decisionId: record.decisionId,
      reason: record.reason,
      riskAcknowledgment: record.riskAcknowledgment,
      complianceCheck: record.complianceCheck,
      businessJustification: record.businessJustification,
      createdBy: record.createdBy,
      createdByName: record.createdByName,
      contentHash: record.contentHash,
      createdAt: record.createdAt.toISOString(),
    };
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let justificationServiceInstance: JustificationService | null = null;

export function getJustificationService(): JustificationService {
  if (!justificationServiceInstance) {
    justificationServiceInstance = JustificationService.getInstance();
  }
  return justificationServiceInstance;
}

export function resetJustificationService(): void {
  justificationServiceInstance = null;
}
