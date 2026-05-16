// ─── Zenic-Agents v3 — HITL API: Approval History ────────────────────
// GET /api/v1/hitl/history — List approval history with filters

import { NextRequest, NextResponse } from "next/server";
import { getApprovalEngine } from "@/lib/hitl";
import { ApprovalRequestStatus, ApprovalPriority, ApprovalType } from "@/lib/hitl";

// GET /api/v1/hitl/history
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const statusParam = searchParams.get("status");
    const priority = searchParams.get("priority") as ApprovalPriority | null;
    const requesterId = searchParams.get("requesterId");
    const type = searchParams.get("type") as ApprovalType | null;
    const targetResource = searchParams.get("targetResource");
    const userId = searchParams.get("userId");
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20));
    const sortBy = (searchParams.get("sortBy") as "createdAt" | "updatedAt" | "priority" | "deadline") ?? "createdAt";
    const sortOrder = (searchParams.get("sortOrder") as "asc" | "desc") ?? "desc";

    // Parse status
    let status: ApprovalRequestStatus | ApprovalRequestStatus[] | undefined;
    if (statusParam) {
      const statuses = statusParam.split(",");
      if (statuses.length === 1) {
        status = statuses[0] as ApprovalRequestStatus;
      } else {
        status = statuses as ApprovalRequestStatus[];
      }
    }

    const engine = getApprovalEngine();
    const result = await engine.getHistory({
      status,
      priority: priority ?? undefined,
      requesterId: requesterId ?? undefined,
      type: type ?? undefined,
      targetResource: targetResource ?? undefined,
      userId: userId ?? undefined,
      page,
      pageSize,
      sortBy,
      sortOrder,
    });

    return NextResponse.json({
      success: true,
      data: result.data,
      total: result.total,
      page: result.page,
      pageSize: result.pageSize,
      totalPages: Math.ceil(result.total / result.pageSize),
    });
  } catch (error) {
    console.error("[HITL GET history]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch approval history", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
