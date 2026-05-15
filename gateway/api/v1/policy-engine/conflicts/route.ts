// ─── Zenic-Agents v3 — Policy Engine API: Conflicts ───────────────────
// GET  /api/v1/policy-engine/conflicts  — List conflicts with filters
// POST /api/v1/policy-engine/conflicts  — Detect conflicts (trigger scan)

import { NextRequest } from "next/server";
import { getConflictDetector } from "@/lib/policy-engine";
import type { ConflictDetectionOptions } from "@/lib/policy-engine/conflict-detector";

// GET /api/v1/policy-engine/conflicts
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    const options: ConflictDetectionOptions = {};

    const severity = searchParams.get("severity");
    if (severity) options.severity = severity as ConflictDetectionOptions["severity"];

    const type = searchParams.get("type");
    if (type) options.type = type as ConflictDetectionOptions["type"];

    const resolved = searchParams.get("resolved");
    if (resolved !== null) options.resolved = resolved === "true";

    const policyId = searchParams.get("policyId");
    if (policyId) options.policyId = policyId;

    const limit = searchParams.get("limit");
    if (limit) options.limit = Math.min(500, Math.max(1, Number(limit)));

    const offset = searchParams.get("offset");
    if (offset) options.offset = Math.max(0, Number(offset));

    const detector = getConflictDetector();
    const conflicts = await detector.getConflicts(options);

    return new Response(
      JSON.stringify({
        success: true,
        data: conflicts,
        total: conflicts.length,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("[Policy-Engine Conflicts GET]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to fetch conflicts",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}

// POST /api/v1/policy-engine/conflicts
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const policyIds: string[] | undefined = body.policyIds;

    const detector = getConflictDetector();
    const report = await detector.detectConflicts(policyIds);

    return new Response(
      JSON.stringify({
        success: true,
        data: report,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    if (error instanceof Error) {
      return new Response(
        JSON.stringify({
          success: false,
          error: error.message,
          code: "DETECTION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }
    console.error("[Policy-Engine Conflicts POST]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to detect conflicts",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
