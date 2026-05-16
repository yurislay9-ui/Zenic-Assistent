// ─── Zenic-Agents v3 — HITL Evidence Service ──────────────────────────
// Phase 5: Evidence attachment to approval requests
//
// Design Patterns:
//   - Singleton: Single service instance via getEvidenceService()
//   - Value Object: Immutable evidence records with SHA-256 content hash
//   - Observer: Records audit events when evidence is attached

import { createHash } from "crypto";
import { db } from "@/lib/db";
import {
  type ApprovalEvidence,
  type AttachEvidenceInput,
  type EvidenceType,
  EvidenceType as EvidenceTypeEnum,
  HitlEventType,
} from "./types";
import { recordAuditEvent } from "./approval-audit";

// ═══════════════════════════════════════════════════════════════════════════
// ID Generation
// ═══════════════════════════════════════════════════════════════════════════

function generateEvidenceId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `evid_${timestamp}_${random}`;
}

// ═══════════════════════════════════════════════════════════════════════════
// Content Hashing
// ═══════════════════════════════════════════════════════════════════════════

/** Compute SHA-256 content hash for evidence immutability */
function computeEvidenceHash(data: {
  requestId: string;
  evidenceType: string;
  content: string;
  source: string;
  description: string;
  timestamp: string;
}): string {
  const canonical = JSON.stringify({
    requestId: data.requestId,
    evidenceType: data.evidenceType,
    content: data.content,
    source: data.source,
    description: data.description,
    timestamp: data.timestamp,
  });
  return createHash("sha256").update(canonical).digest("hex");
}

// ═══════════════════════════════════════════════════════════════════════════
// Evidence Service (Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class EvidenceService {
  private static instance: EvidenceService | null = null;

  private constructor() {}

  static getInstance(): EvidenceService {
    if (!EvidenceService.instance) {
      EvidenceService.instance = new EvidenceService();
    }
    return EvidenceService.instance;
  }

  /** Attach evidence to an approval request */
  async attachEvidence(requestId: string, input: AttachEvidenceInput): Promise<ApprovalEvidence> {
    // Validate the request exists
    const request = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!request) {
      throw new Error(`Approval request "${requestId}" not found`);
    }

    // Validate evidence type
    const validTypes = Object.values(EvidenceTypeEnum) as string[];
    if (!validTypes.includes(input.evidenceType)) {
      throw new Error(
        `Invalid evidence type "${input.evidenceType}". Must be one of: ${validTypes.join(", ")}`,
      );
    }

    const evidenceId = generateEvidenceId();
    const timestamp = new Date().toISOString();
    const contentStr = JSON.stringify(input.content);
    const description = input.description ?? "";

    const contentHash = computeEvidenceHash({
      requestId,
      evidenceType: input.evidenceType,
      content: contentStr,
      source: input.source,
      description,
      timestamp,
    });

    const record = await db.hitlEvidence.create({
      data: {
        evidenceId,
        requestId,
        evidenceType: input.evidenceType,
        content: contentStr,
        contentHash,
        source: input.source,
        description,
      },
    });

    // Record audit event
    await recordAuditEvent({
      requestId,
      eventType: "created" as HitlEventType,
      actorId: input.source,
      actorName: input.source,
      details: {
        action: "evidence_attached",
        evidenceId,
        evidenceType: input.evidenceType,
        contentHash,
        description,
      },
    });

    return this.mapRecordToModel(record);
  }

  /** Get all evidence for an approval request */
  async getEvidence(requestId: string): Promise<ApprovalEvidence[]> {
    const records = await db.hitlEvidence.findMany({
      where: { requestId },
      orderBy: { createdAt: "asc" },
    });

    return records.map((r) => this.mapRecordToModel(r));
  }

  /** Get evidence for a request filtered by type */
  async getEvidenceByType(requestId: string, evidenceType: EvidenceType): Promise<ApprovalEvidence[]> {
    const records = await db.hitlEvidence.findMany({
      where: { requestId, evidenceType },
      orderBy: { createdAt: "asc" },
    });

    return records.map((r) => this.mapRecordToModel(r));
  }

  /** Verify the integrity of an evidence record by recomputing its content hash */
  async verifyEvidenceIntegrity(evidenceId: string): Promise<{
    valid: boolean;
    evidenceId: string;
  }> {
    const record = await db.hitlEvidence.findUnique({
      where: { evidenceId },
    });

    if (!record) {
      throw new Error(`Evidence "${evidenceId}" not found`);
    }

    const expectedHash = computeEvidenceHash({
      requestId: record.requestId,
      evidenceType: record.evidenceType,
      content: record.content,
      source: record.source,
      description: record.description,
      timestamp: record.createdAt.toISOString(),
    });

    return {
      valid: record.contentHash === expectedHash,
      evidenceId: record.evidenceId,
    };
  }

  /** Map a database record to the domain model */
  private mapRecordToModel(record: {
    id: string;
    evidenceId: string;
    requestId: string;
    evidenceType: string;
    content: string;
    contentHash: string;
    source: string;
    description: string;
    createdAt: Date;
  }): ApprovalEvidence {
    return {
      evidenceId: record.evidenceId,
      requestId: record.requestId,
      evidenceType: record.evidenceType as EvidenceType,
      content: JSON.parse(record.content),
      contentHash: record.contentHash,
      source: record.source,
      description: record.description,
      createdAt: record.createdAt.toISOString(),
    };
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let evidenceServiceInstance: EvidenceService | null = null;

export function getEvidenceService(): EvidenceService {
  if (!evidenceServiceInstance) {
    evidenceServiceInstance = EvidenceService.getInstance();
  }
  return evidenceServiceInstance;
}

export function resetEvidenceService(): void {
  evidenceServiceInstance = null;
}
