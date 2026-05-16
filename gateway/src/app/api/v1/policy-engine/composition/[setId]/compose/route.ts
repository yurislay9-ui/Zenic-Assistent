// ─── Zenic-Agents v3 — Policy Engine API: Compose Policy Set ─────────
// POST /api/v1/policy-engine/composition/[setId]/compose — Compose a policy set

import { NextRequest } from "next/server";
import { getCompositionEngine } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/composition/[setId]/compose
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ setId: string }> },
) {
  try {
    const { setId } = await params;
    const engine = getCompositionEngine();
    const result = await engine.composePolicySet(setId);

    return new Response(
      JSON.stringify({
        success: true,
        data: result,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    if (error instanceof Error) {
      if (error.message.includes("not found")) {
        return new Response(
          JSON.stringify({
            success: false,
            error: error.message,
            code: "NOT_FOUND",
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(
        JSON.stringify({
          success: false,
          error: error.message,
          code: "COMPOSITION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }
    console.error("[Policy-Engine Compose POST]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to compose policy set",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
