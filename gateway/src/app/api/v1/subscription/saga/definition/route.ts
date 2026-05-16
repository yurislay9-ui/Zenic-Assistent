// ─── GET /api/v1/subscription/saga/definition?sagaType=xxx ──────────────
import { NextRequest, NextResponse } from "next/server";
import { getSagaDefinition } from "@/lib/pricing-engine/saga";
import type { SagaTypeName } from "@/lib/pricing-engine/saga";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const sagaType = searchParams.get("sagaType") as SagaTypeName;

    if (!sagaType) {
      return NextResponse.json({ error: "sagaType query parameter is required" }, { status: 400 });
    }

    const definition = getSagaDefinition(sagaType);
    if (!definition) {
      return NextResponse.json({ error: `Unknown saga type: ${sagaType}` }, { status: 404 });
    }

    return NextResponse.json(definition);
  } catch (error) {
    return NextResponse.json({ error: "Failed to get saga definition", details: String(error) }, { status: 500 });
  }
}
