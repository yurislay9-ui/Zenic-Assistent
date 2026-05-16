// ─── POST /api/v1/subscription/saga/retry ──────────────────────────────
// Resume a paused saga (e.g., after admin confirms payment)
import { NextRequest, NextResponse } from "next/server";
import { resumeSaga } from "@/lib/pricing-engine/saga";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { executionId, resumeInput } = body as {
      executionId: string;
      resumeInput?: Record<string, unknown>;
    };

    if (!executionId) {
      return NextResponse.json({ error: "executionId is required" }, { status: 400 });
    }

    const result = await resumeSaga(executionId, resumeInput || {});

    return NextResponse.json({
      execution_id: result.executionId,
      saga_type: result.sagaType,
      status: result.status,
      current_step_index: result.currentStepIndex,
      total_steps: result.totalSteps,
      completed_steps: result.completedSteps,
      error_message: result.errorMessage,
      compensation_reason: result.compensationReason,
      payment_currency: "USDT",
      payment_network: "TRC20",
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to resume saga", details: String(error) }, { status: 500 });
  }
}
