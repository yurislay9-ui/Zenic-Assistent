// ─── Zenic-Agents v3 — Policy Engine API: Simulations ────────────────
// GET  /api/v1/policy-engine/simulations  — List simulations
// POST /api/v1/policy-engine/simulations  — Run a what-if simulation

import { NextRequest, NextResponse } from "next/server";
import {
  listSimulations,
  runSimulation,
} from "@/lib/policy-engine";
import type { SimulationRequest } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/simulations
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const requestedBy = searchParams.get("requestedBy") ?? undefined;
    const riskLevel = searchParams.get("riskLevel") ?? undefined;
    const limit = Math.min(200, Math.max(1, Number(searchParams.get("limit")) || 50));
    const offset = Math.max(0, Number(searchParams.get("offset")) || 0);

    const simulations = await listSimulations({
      requestedBy,
      riskLevel: riskLevel as "low" | "medium" | "high" | "critical" | undefined,
      limit,
      offset,
    });

    return NextResponse.json({
      success: true,
      data: simulations,
      count: simulations.length,
      limit,
      offset,
    });
  } catch (error) {
    console.error("[Policy-Engine Simulations GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to list simulations", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// POST /api/v1/policy-engine/simulations
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validate required fields
    if (!body.name || !body.proposedChanges || !body.testRequests || !body.requestedBy) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: name, proposedChanges, testRequests, requestedBy",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const simulationRequest: SimulationRequest = {
      name: body.name,
      description: body.description ?? "",
      proposedChanges: body.proposedChanges,
      testRequests: body.testRequests,
      includeTrace: body.includeTrace ?? false,
      requestedBy: body.requestedBy,
    };

    const result = await runSimulation(simulationRequest);

    return NextResponse.json({
      success: true,
      data: result,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error) {
      return NextResponse.json(
        { success: false, error: error.message, code: "SIMULATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Policy-Engine Simulations POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to run simulation", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
