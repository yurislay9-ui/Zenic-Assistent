// ─── Zenic-Agents v3 — Policy Engine API: Resolve Conflict ───────────
// POST /api/v1/policy-engine/conflicts/[conflictId]/resolve — Resolve a conflict

import { NextRequest } from "next/server";
import { getConflictDetector } from "@/lib/policy-engine";
import type { ConflictResolutionStrategy } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/conflicts/[conflictId]/resolve
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ conflictId: string }> },
) {
  try {
    const { conflictId } = await params;
    const body = await request.json();

    const strategy = body.strategy as ConflictResolutionStrategy | undefined;
    const resolvedBy = body.resolvedBy as string | undefined;
    const note = body.note as string | undefined;

    if (!strategy) {
      return new Response(
        JSON.stringify({
          success: false,
          error: "Missing required field: strategy",
          code: "VALIDATION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    if (!resolvedBy) {
      return new Response(
        JSON.stringify({
          success: false,
          error: "Missing required field: resolvedBy",
          code: "VALIDATION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    const detector = getConflictDetector();
    const resolved = await detector.resolveConflict(
      conflictId,
      strategy,
      resolvedBy,
      note ?? "",
    );

    if (!resolved) {
      return new Response(
        JSON.stringify({
          success: false,
          error: `Conflict "${conflictId}" not found`,
          code: "NOT_FOUND",
        }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      );
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: resolved,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    if (error instanceof Error) {
      return new Response(
        JSON.stringify({
          success: false,
          error: error.message,
          code: "RESOLUTION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }
    console.error("[Policy-Engine Conflict Resolve POST]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to resolve conflict",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
