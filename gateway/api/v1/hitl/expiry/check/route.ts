// ─── Zenic-Agents v3 — HITL API: Check and Process Expired Requests ──
// POST /api/v1/hitl/expiry/check

import { NextResponse } from "next/server";
import { getExpiryService } from "@/lib/hitl";

// POST /api/v1/hitl/expiry/check
export async function POST() {
  try {
    const service = getExpiryService();
    const expired = await service.checkExpired();

    const reverted: Array<{ requestId: string; success: boolean }> = [];

    for (const record of expired) {
      if (record.autoRevertEnabled && record.status !== "reverted") {
        try {
          const result = await service.executeRevert(record.requestId);
          reverted.push({ requestId: record.requestId, success: result.success });
        } catch {
          reverted.push({ requestId: record.requestId, success: false });
        }
      }
    }

    return NextResponse.json({
      success: true,
      data: {
        expired,
        reverted,
      },
    });
  } catch (error) {
    console.error("[HITL POST expiry/check]", error);
    return NextResponse.json(
      { success: false, error: "Failed to check expired requests", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
