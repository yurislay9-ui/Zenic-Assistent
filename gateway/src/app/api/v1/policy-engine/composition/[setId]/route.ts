// ─── Zenic-Agents v3 — Policy Engine API: Policy Set Get/Delete ──────
// GET    /api/v1/policy-engine/composition/[setId]  — Get a policy set
// DELETE /api/v1/policy-engine/composition/[setId]  — Delete a policy set

import { NextRequest } from "next/server";
import { getCompositionEngine } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/composition/[setId]
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ setId: string }> },
) {
  try {
    const { setId } = await params;
    const engine = getCompositionEngine();
    const policySet = await engine.getPolicySet(setId);

    if (!policySet) {
      return new Response(
        JSON.stringify({
          success: false,
          error: `PolicySet "${setId}" not found`,
          code: "NOT_FOUND",
        }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      );
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: policySet,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("[Policy-Engine Composition GET by setId]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to fetch policy set",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}

// DELETE /api/v1/policy-engine/composition/[setId]
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ setId: string }> },
) {
  try {
    const { setId } = await params;
    const engine = getCompositionEngine();

    await engine.deletePolicySet(setId);

    return new Response(
      JSON.stringify({
        success: true,
        data: { setId, deleted: true },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    if (error instanceof Error && error.message.includes("not found")) {
      return new Response(
        JSON.stringify({
          success: false,
          error: error.message,
          code: "NOT_FOUND",
        }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      );
    }
    console.error("[Policy-Engine Composition DELETE]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to delete policy set",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
