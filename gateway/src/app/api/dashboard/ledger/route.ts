import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const entries = await db.hitlApprovalAudit.findMany({
      orderBy: { timestamp: "desc" },
      take: 10,
    });

    const formatted = entries.map((e) => ({
      id: e.id,
      requestId: e.requestId,
      eventType: e.eventType,
      actorName: e.actorName,
      contentHash: e.contentHash,
      previousHash: e.previousHash ?? null,
      timestamp: e.timestamp.toISOString(),
    }));

    return NextResponse.json({ entries: formatted });
  } catch (error) {
    console.error("[/api/dashboard/ledger GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch Merkle audit trail" },
      { status: 500 }
    );
  }
}
