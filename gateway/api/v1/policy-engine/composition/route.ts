// ─── Zenic-Agents v3 — Policy Engine API: Composition ────────────────
// GET  /api/v1/policy-engine/composition  — List policy sets
// POST /api/v1/policy-engine/composition  — Create a policy set

import { NextRequest } from "next/server";
import { getCompositionEngine } from "@/lib/policy-engine";
import type { PolicySet } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/composition
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const namespace = searchParams.get("namespace") ?? undefined;

    const engine = getCompositionEngine();
    const policySets = await engine.listPolicySets(namespace);

    return new Response(
      JSON.stringify({
        success: true,
        data: policySets,
        total: policySets.length,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("[Policy-Engine Composition GET]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to list policy sets",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}

// POST /api/v1/policy-engine/composition
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const policySet = body as PolicySet;

    if (!policySet.apiVersion || !policySet.kind || !policySet.metadata) {
      return new Response(
        JSON.stringify({
          success: false,
          error: "Invalid PolicySet: apiVersion, kind, and metadata are required",
          code: "VALIDATION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    if (!policySet.metadata.id || !policySet.metadata.name) {
      return new Response(
        JSON.stringify({
          success: false,
          error: "Invalid PolicySet metadata: id and name are required",
          code: "VALIDATION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }

    const engine = getCompositionEngine();
    const created = await engine.createPolicySet(policySet);

    return new Response(
      JSON.stringify({
        success: true,
        data: created,
      }),
      { status: 201, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    if (error instanceof Error) {
      return new Response(
        JSON.stringify({
          success: false,
          error: error.message,
          code: "COMPOSITION_ERROR",
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      );
    }
    console.error("[Policy-Engine Composition POST]", error);
    return new Response(
      JSON.stringify({
        success: false,
        error: "Failed to create policy set",
        code: "INTERNAL_ERROR",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
