// ─── Zenic-Agents v3 — Policy Engine API: Simulation by ID ───────────
// GET    /api/v1/policy-engine/simulations/[simulationId]  — Get simulation result
// DELETE /api/v1/policy-engine/simulations/[simulationId]  — Delete a simulation

import { NextRequest, NextResponse } from "next/server";
import {
  getSimulation,
  deleteSimulation,
} from "@/lib/policy-engine";

// GET /api/v1/policy-engine/simulations/[simulationId]
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ simulationId: string }> },
) {
  try {
    const { simulationId } = await params;

    const result = await getSimulation(simulationId);

    if (!result) {
      return NextResponse.json(
        { success: false, error: `Simulation "${simulationId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[Policy-Engine Simulation GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch simulation", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// DELETE /api/v1/policy-engine/simulations/[simulationId]
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ simulationId: string }> },
) {
  try {
    const { simulationId } = await params;

    const deleted = await deleteSimulation(simulationId);

    if (!deleted) {
      return NextResponse.json(
        { success: false, error: `Simulation "${simulationId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: { simulationId, deleted: true },
    });
  } catch (error) {
    console.error("[Policy-Engine Simulation DELETE]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete simulation", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
