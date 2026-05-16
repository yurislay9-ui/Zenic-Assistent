// ─── Zenic-Agents v3 — HITL API: Get Notification History for User ───
// GET /api/v1/hitl/notifications/[userId]

import { NextRequest, NextResponse } from "next/server";
import { getNotificationLogService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ userId: string }>;
}

// GET /api/v1/hitl/notifications/[userId]
export async function GET(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { userId } = await params;
    const { searchParams } = new URL(request.url);
    const channel = searchParams.get("channel") ?? undefined;
    const event = searchParams.get("event") ?? undefined;
    const status = searchParams.get("status") ?? undefined;
    const limit = Math.min(200, Math.max(1, Number(searchParams.get("limit")) || 20));

    const service = getNotificationLogService();
    const result = await service.getNotificationHistoryForUser(userId, {
      channel,
      event,
      status,
      limit,
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[HITL GET notifications/userId]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch notification history", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
