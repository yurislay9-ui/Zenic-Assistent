// ─── Zenic-Agents v3 — Playbooks API: Onboarding ────────────────────
// POST /api/v1/playbooks/onboarding — Create onboarding session
// GET  /api/v1/playbooks/onboarding — Get onboarding session progress

import { NextRequest, NextResponse } from "next/server";
import {
  createOnboardingSession,
  getOnboardingProgress,
} from "@/lib/playbooks";

// POST /api/v1/playbooks/onboarding
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { playbookId, tenantId } = body;

    if (!playbookId) {
      return NextResponse.json(
        { error: "playbookId is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const session = await createOnboardingSession(playbookId, tenantId);

    return NextResponse.json(session, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    if (message.includes("not found") || message.includes("not active")) {
      return NextResponse.json(
        { error: message, code: "NOT_FOUND" },
        { status: 404 },
      );
    }
    console.error("[Playbooks Onboarding POST]", error);
    return NextResponse.json(
      { error: "Failed to create onboarding session", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// GET /api/v1/playbooks/onboarding
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const sessionId = searchParams.get("sessionId");

    if (!sessionId) {
      return NextResponse.json(
        { error: "sessionId query parameter is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const progress = await getOnboardingProgress(sessionId);

    if (progress.totalSteps === 0) {
      return NextResponse.json(
        { error: `Session "${sessionId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json(progress);
  } catch (error) {
    console.error("[Playbooks Onboarding GET]", error);
    return NextResponse.json(
      { error: "Failed to get onboarding progress", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
