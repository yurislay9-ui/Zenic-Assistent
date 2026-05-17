// ─── Zenic-Agents v3 — HITL Pipeline Integration ──────────────────────
// Phase 5: Adapter pattern — Connects HITL with SafetyGate + PolicyEngine
//
// When SafetyGate returns CONFIRM/APPROVE, this module creates the HITL request
// When PolicyEngine returns REQUIRE_APPROVAL, this module creates the HITL request
//
// Design Patterns:
//   - Adapter: Translates pipeline-specific verdicts into HITL requests
//   - Singleton: Single integration instance
//   - Strategy: Category/risk mapping strategies

import {
  type ApprovalRequest,
  type ExpiryRecord,
  type EscalationSLA,
  type ApprovalType,
  type ApprovalPriority,
  ApprovalType as ApprovalTypeEnum,
  ApprovalPriority as ApprovalPriorityEnum,
} from "./types";
import { getApprovalEngine } from "./approval-engine";
import { getExpiryService } from "./expiry-service";
import { getSLAService } from "./sla-service";
import { recordAuditEvent } from "./approval-audit";
import { HitlEventType } from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// Pipeline Integration Types
// ═══════════════════════════════════════════════════════════════════════════

/** Safety gate verdict that requires human approval */
export interface SafetyGateVerdict {
  /** Unique action identifier */
  actionId: string;
  /** Type of action being evaluated */
  actionType: string;
  /** Verdict from the safety gate */
  verdict: "confirm" | "approve" | "deny";
  /** Safety category (e.g., "data_modification", "system_config", "financial") */
  category: string;
  /** Risk level assessed by the safety gate */
  riskLevel?: string;
  /** Reason for the verdict */
  reason?: string;
}

/** Policy engine result that requires approval */
export interface PolicyApprovalRequirement {
  /** Policy ID that triggered the requirement */
  policyId: string;
  /** Statement ID within the policy */
  statementId: string;
  /** Effect from the policy evaluation */
  effect: "require_approval" | "escalate";
  /** Required role for approval (from policy statement) */
  requiredRole?: string;
  /** Reason from the policy evaluation */
  reason?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// Category/Risk Mapping Tables
// ═══════════════════════════════════════════════════════════════════════════

/** Map safety categories to approval types */
const CATEGORY_TO_TYPE: Record<string, ApprovalType> = {
  data_modification: ApprovalTypeEnum.DATA_ACCESS,
  data_access: ApprovalTypeEnum.DATA_ACCESS,
  system_config: ApprovalTypeEnum.CONFIGURATION,
  configuration: ApprovalTypeEnum.CONFIGURATION,
  deployment: ApprovalTypeEnum.DEPLOYMENT,
  release: ApprovalTypeEnum.DEPLOYMENT,
  financial: ApprovalTypeEnum.FINANCIAL,
  payment: ApprovalTypeEnum.FINANCIAL,
  security: ApprovalTypeEnum.SECURITY,
  authentication: ApprovalTypeEnum.SECURITY,
  policy_change: ApprovalTypeEnum.POLICY_CHANGE,
  policy: ApprovalTypeEnum.POLICY_CHANGE,
  action: ApprovalTypeEnum.ACTION_APPROVAL,
  general: ApprovalTypeEnum.ACTION_APPROVAL,
};

/** Map risk levels to approval priorities */
const RISK_TO_PRIORITY: Record<string, ApprovalPriority> = {
  critical: ApprovalPriorityEnum.CRITICAL,
  emergency: ApprovalPriorityEnum.EMERGENCY,
  high: ApprovalPriorityEnum.HIGH,
  medium: ApprovalPriorityEnum.MEDIUM,
  low: ApprovalPriorityEnum.LOW,
};

/** Categories where actions are generally reversible */
const REVERSIBLE_CATEGORIES = new Set([
  "data_modification",
  "system_config",
  "configuration",
  "policy_change",
  "policy",
]);

/** Action types that are generally reversible */
const REVERSIBLE_ACTION_TYPES = new Set([
  "database_write",
  "config_change",
  "policy_change",
  "deployment",
  "financial_transfer",
]);

// ═══════════════════════════════════════════════════════════════════════════
// Pipeline Integration (Adapter + Singleton)
// ═══════════════════════════════════════════════════════════════════════════

class PipelineIntegration {
  private static instance: PipelineIntegration | null = null;

  private constructor() {}

  static getInstance(): PipelineIntegration {
    if (!PipelineIntegration.instance) {
      PipelineIntegration.instance = new PipelineIntegration();
    }
    return PipelineIntegration.instance;
  }

  /** Create HITL request from SafetyGate verdict */
  async createFromSafetyGate(
    verdict: SafetyGateVerdict,
    requesterId: string,
    requesterName: string,
    actionPayload?: Record<string, unknown>,
  ): Promise<{
    request: ApprovalRequest;
    expiry: ExpiryRecord;
    sla: EscalationSLA;
  } | null> {
    // If verdict is DENY, return null — DENY is invariant
    // FIX #4: Antes intentaba grabar audit con requestId inventado
    // ("denied_XXX") que violaba FK en HitlApprovalAudit.requestId.
    // DENY es absoluto — no crea solicitud HITL ni registro de auditoría HITL.
    // El deny ya se registra en AuditLog (tabla general) por el SafetyGate.
    if (verdict.verdict === "deny") {
      return null;
    }

    const engine = getApprovalEngine();
    const expiryService = getExpiryService();
    const slaService = getSLAService();

    // Determine priority from category and risk level
    const priority = this.mapRiskToPriority(verdict.riskLevel);

    // Determine approval type from category
    const type = this.mapCategoryToType(verdict.category);

    // Determine if action is reversible
    const isReversible = this.isActionReversible(verdict.category, verdict.actionType);

    // Build the request
    const request = await engine.createRequest({
      title: `[Safety Gate] ${verdict.actionType} — ${verdict.category}`,
      description: verdict.reason ?? `Safety gate requires human approval for action "${verdict.actionType}" in category "${verdict.category}"`,
      type,
      priority,
      requesterId,
      requesterName,
      targetResource: verdict.actionId,
      targetAction: verdict.actionType,
      actionPayload: {
        ...actionPayload,
        _safetyGateVerdict: verdict.verdict,
        _safetyGateCategory: verdict.category,
        _safetyGateRiskLevel: verdict.riskLevel,
        _safetyGateReason: verdict.reason,
      },
      isReversible,
      tags: ["safety_gate", verdict.category, verdict.verdict],
      metadata: {
        source: "safety_gate",
        actionId: verdict.actionId,
        verdict: verdict.verdict,
        category: verdict.category,
        riskLevel: verdict.riskLevel,
      },
    });

    // Set auto-revert based on action category
    const autoRevert = isReversible;
    const expiry = await expiryService.setExpiry(request.requestId, {
      autoRevertEnabled: autoRevert,
      revertAction: actionPayload ?? {},
    });

    // Create SLA with appropriate level
    const sla = await slaService.createSLA(request.requestId);

    // Record audit event
    await recordAuditEvent({
      requestId: request.requestId,
      eventType: HitlEventType.CREATED,
      actorId: "safety_gate",
      actorName: "Safety Gate",
      details: {
        action: "hitl_from_safety_gate",
        actionId: verdict.actionId,
        verdict: verdict.verdict,
        category: verdict.category,
        riskLevel: verdict.riskLevel,
        approvalType: type,
        priority,
        isReversible,
      },
    });

    return { request, expiry, sla };
  }

  /** Create HITL request from PolicyEngine result */
  async createFromPolicyEngine(
    requirement: PolicyApprovalRequirement,
    requesterId: string,
    requesterName: string,
    targetResource: string,
    targetAction: string,
    actionPayload?: Record<string, unknown>,
  ): Promise<{
    request: ApprovalRequest;
    expiry: ExpiryRecord;
    sla: EscalationSLA;
  }> {
    const engine = getApprovalEngine();
    const expiryService = getExpiryService();
    const slaService = getSLAService();

    // Use required role from policy statement
    const requiredRole = requirement.requiredRole;

    // Determine priority based on effect
    const priority: ApprovalPriority = requirement.effect === "escalate"
      ? ApprovalPriorityEnum.HIGH
      : ApprovalPriorityEnum.MEDIUM;

    // Determine approval type from target action
    const type = this.mapCategoryToType(targetAction);

    const request = await engine.createRequest({
      title: `[Policy Engine] ${targetAction} — ${requirement.policyId}`,
      description: requirement.reason ?? `Policy "${requirement.policyId}" statement "${requirement.statementId}" requires approval for action "${targetAction}"`,
      type,
      priority,
      requesterId,
      requesterName,
      targetResource,
      targetAction,
      actionPayload: {
        ...actionPayload,
        _policyId: requirement.policyId,
        _statementId: requirement.statementId,
        _policyEffect: requirement.effect,
        _requiredRole: requiredRole,
      },
      tags: ["policy_engine", requirement.effect, requirement.policyId],
      metadata: {
        source: "policy_engine",
        policyId: requirement.policyId,
        statementId: requirement.statementId,
        effect: requirement.effect,
        requiredRole,
      },
      approvalPolicy: requiredRole ? {
        mode: "single",
        requiredRoles: [requiredRole],
      } : undefined,
    });

    // Set expiry
    const expiry = await expiryService.setExpiry(request.requestId, {
      autoRevertEnabled: true,
      revertAction: actionPayload ?? {},
    });

    // Create SLA with appropriate level
    // If the effect is "escalate", start at a higher level
    const initialLevel = requirement.effect === "escalate" ? 1 : 0;
    const sla = await slaService.createSLA(request.requestId, initialLevel);

    // Record audit event
    await recordAuditEvent({
      requestId: request.requestId,
      eventType: HitlEventType.CREATED,
      actorId: "policy_engine",
      actorName: "Policy Engine",
      details: {
        action: "hitl_from_policy_engine",
        policyId: requirement.policyId,
        statementId: requirement.statementId,
        effect: requirement.effect,
        requiredRole,
        priority,
        initialLevel,
      },
    });

    return { request, expiry, sla };
  }

  /** Map safety category to approval type */
  private mapCategoryToType(category: string): ApprovalType {
    const normalized = category.toLowerCase().replace(/[\s-]/g, "_");
    return CATEGORY_TO_TYPE[normalized] ?? ApprovalTypeEnum.ACTION_APPROVAL;
  }

  /** Map safety risk to approval priority */
  private mapRiskToPriority(riskLevel?: string): ApprovalPriority {
    if (!riskLevel) return ApprovalPriorityEnum.MEDIUM;
    const normalized = riskLevel.toLowerCase();
    return RISK_TO_PRIORITY[normalized] ?? ApprovalPriorityEnum.MEDIUM;
  }

  /** Determine if action is reversible based on category */
  private isActionReversible(category: string, actionType: string): boolean {
    const normalizedCategory = category.toLowerCase().replace(/[\s-]/g, "_");
    const normalizedAction = actionType.toLowerCase().replace(/[\s-]/g, "_");
    return REVERSIBLE_CATEGORIES.has(normalizedCategory) || REVERSIBLE_ACTION_TYPES.has(normalizedAction);
  }
}

// ─── Singleton Accessors ──────────────────────────────────────────────

let integrationInstance: PipelineIntegration | null = null;

export function getPipelineIntegration(): PipelineIntegration {
  if (!integrationInstance) {
    integrationInstance = PipelineIntegration.getInstance();
  }
  return integrationInstance;
}

export function resetPipelineIntegration(): void {
  integrationInstance = null;
  PipelineIntegration.instance = null; // FIX #5
}
