import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    // Get pending HITL approval requests that are memory/learning related
    // Filter by types related to memory proposals: action_approval, policy_change, data_access
    const proposals = await db.hitlApprovalRequest.findMany({
      where: {
        status: "pending",
        type: { in: ["action_approval", "policy_change", "data_access"] },
      },
      orderBy: { createdAt: "desc" },
    });

    const formatted = proposals.map((p) => {
      // Parse metadata for LLM verdict
      let llmVerdict = false;
      try {
        const meta = JSON.parse(p.metadata);
        llmVerdict = meta?.llmVerdict ?? false;
      } catch {
        // ignore parse errors
      }

      return {
        id: p.id,
        requestId: p.requestId,
        title: p.title,
        description: p.description,
        type: p.type,
        status: p.status,
        priority: p.priority,
        requesterName: p.requesterName,
        targetAction: p.targetAction,
        createdAt: p.createdAt.toISOString(),
        llmVerdict,
      };
    });

    return NextResponse.json({ proposals: formatted });
  } catch (error) {
    console.error("[/api/dashboard/memory-proposals GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch memory proposals" },
      { status: 500 }
    );
  }
}
