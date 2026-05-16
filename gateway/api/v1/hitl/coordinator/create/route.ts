// ─── Zenic-Agents v3 — HITL API: Coordinator Create Full Request ──────
// POST /api/v1/hitl/coordinator/create

import { NextRequest, NextResponse } from "next/server";
import { getHITLCoordinator } from "@/lib/hitl";

// POST /api/v1/hitl/coordinator/create
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validate required fields for the base request
    if (!body.title || !body.description || !body.type || !body.requesterId || !body.requesterName || !body.targetResource || !body.targetAction) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: title, description, type, requesterId, requesterName, targetResource, targetAction",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    // Validate type
    const validTypes: string[] = ["action_approval", "policy_change", "deployment", "data_access", "configuration", "financial", "security"];
    if (!validTypes.includes(body.type)) {
      return NextResponse.json(
        { success: false, error: `Invalid type. Must be one of: ${validTypes.join(", ")}`, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Validate priority if provided
    if (body.priority) {
      const validPriorities: string[] = ["low", "medium", "high", "critical", "emergency"];
      if (!validPriorities.includes(body.priority)) {
        return NextResponse.json(
          { success: false, error: `Invalid priority. Must be one of: ${validPriorities.join(", ")}`, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }

    // Validate justification if provided
    if (body.justification) {
      if (!body.justification.reason || body.justification.riskAcknowledgment === undefined || body.justification.complianceCheck === undefined || !body.justification.createdBy || !body.justification.createdByName) {
        return NextResponse.json(
          {
            success: false,
            error: "Justification requires: reason, riskAcknowledgment, complianceCheck, createdBy, createdByName",
            code: "VALIDATION_ERROR",
          },
          { status: 400 },
        );
      }
    }

    const coordinator = getHITLCoordinator();
    const result = await coordinator.createFullRequest({
      title: body.title,
      description: body.description,
      type: body.type,
      priority: body.priority,
      requesterId: body.requesterId,
      requesterName: body.requesterName,
      targetResource: body.targetResource,
      targetAction: body.targetAction,
      actionPayload: body.actionPayload,
      undoPayload: body.undoPayload,
      isReversible: body.isReversible,
      undoWindowMs: body.undoWindowMs,
      deadline: body.deadline,
      requiredApprovals: body.requiredApprovals,
      approvalPolicy: body.approvalPolicy,
      parentId: body.parentId,
      tags: body.tags,
      metadata: body.metadata,
      evidence: body.evidence,
      justification: body.justification,
      autoRevertOnExpiry: body.autoRevertOnExpiry,
      revertAction: body.revertAction,
      expiryNotificationSchedule: body.expiryNotificationSchedule,
    });

    return NextResponse.json({
      success: true,
      data: result,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error) {
      if (error.message.includes("validation failed")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }
    console.error("[HITL POST coordinator/create]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create full approval request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
