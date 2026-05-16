import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const now = new Date();
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    // Fetch all tool executions from the last 24 hours
    const executions = await db.toolExecution.findMany({
      where: { createdAt: { gte: last24h } },
      select: {
        createdAt: true,
        verdict: true,
        status: true,
      },
    });

    // Build hourly segments
    const segments: Array<{
      hour: string;
      allowed: number;
      confirmed: number;
      blocked: number;
    }> = [];

    for (let h = 0; h < 24; h++) {
      const hourStr = `${h.toString().padStart(2, "0")}:00`;
      const hourEntries = executions.filter((e) => e.createdAt.getHours() === h);

      const allowed = hourEntries.filter(
        (e) => e.verdict === "allow" && e.status === "completed"
      ).length;

      const confirmed = hourEntries.filter(
        (e) => e.verdict === "conditional" || (e.verdict === "allow" && e.status === "approved")
      ).length;

      const blocked = hourEntries.filter(
        (e) => e.verdict === "deny"
      ).length;

      segments.push({ hour: hourStr, allowed, confirmed, blocked });
    }

    return NextResponse.json({ segments });
  } catch (error) {
    console.error("[/api/dashboard/heatmap GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch verdict heatmap" },
      { status: 500 }
    );
  }
}
