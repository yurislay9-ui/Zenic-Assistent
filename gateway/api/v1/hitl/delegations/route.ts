// ─── Zenic-Agents v3 — HITL API: Delegation Rules ────────────────────
// GET  /api/v1/hitl/delegations — List delegation rules
// POST /api/v1/hitl/delegations — Create a delegation rule

import { NextRequest, NextResponse } from "next/server";
import { getDelegationService } from "@/lib/hitl";

// GET /api/v1/hitl/delegations
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const fromUserId = searchParams.get("fromUserId");
    const isActive = searchParams.get("isActive");

    const service = getDelegationService();
    const data = await service.listDelegationRules({
      fromUserId: fromUserId ?? undefined,
      isActive: isActive !== null ? isActive === "true" : undefined,
    });

    return NextResponse.json({
      success: true,
      data,
      total: data.length,
    });
  } catch (error) {
    console.error("[HITL GET delegations]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch delegation rules", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// POST /api/v1/hitl/delegations
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.fromUserId || !body.toUserId || !body.toUserName || !body.ruleName) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: fromUserId, toUserId, toUserName, ruleName",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const service = getDelegationService();
    const result = await service.createDelegationRule({
      fromUserId: body.fromUserId,
      toUserId: body.toUserId,
      toUserName: body.toUserName,
      ruleName: body.ruleName,
      description: body.description,
      maxDepth: body.maxDepth,
      expiresAt: body.expiresAt,
    });

    return NextResponse.json({
      success: true,
      data: result,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error) {
      if (error.message.includes("yourself") || error.message.includes("Maximum delegation depth")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }
    console.error("[HITL POST delegations]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create delegation rule", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
