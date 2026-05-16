// ─── GET /api/v1/subscription/saga/status?executionId=xxx ───────────────
import { NextRequest, NextResponse } from "next/server";
import { getSagaStatus, getSagasForTenant } from "@/lib/pricing-engine/saga";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const executionId = searchParams.get("executionId");
    const tenantId = searchParams.get("tenantId");

    if (executionId) {
      const status = await getSagaStatus(executionId);
      if (!status) {
        return NextResponse.json({ error: "Saga execution not found" }, { status: 404 });
      }
      return NextResponse.json(status);
    }

    if (tenantId) {
      const sagas = await getSagasForTenant(tenantId);
      return NextResponse.json({ sagas });
    }

    return NextResponse.json({ error: "Provide executionId or tenantId query parameter" }, { status: 400 });
  } catch (error) {
    return NextResponse.json({ error: "Failed to get saga status", details: String(error) }, { status: 500 });
  }
}
