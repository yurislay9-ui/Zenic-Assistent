// ─── GET /api/v1/subscription/saga/types ──────────────────────────────
import { NextResponse } from "next/server";
import { getSagaTypes } from "@/lib/pricing-engine/saga";

export async function GET() {
  try {
    const types = getSagaTypes();
    return NextResponse.json({
      saga_types: types,
      payment_currency: "USDT",
      payment_network: "TRC20",
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to get saga types", details: String(error) }, { status: 500 });
  }
}
