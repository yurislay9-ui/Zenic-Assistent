import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const now = new Date();
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    const alerts = await db.auditLog.findMany({
      where: {
        severity: { in: ["warn", "error", "critical"] },
        createdAt: { gte: last24h },
      },
      orderBy: { createdAt: "desc" },
    });

    const formatted = alerts.map((a) => {
      // Extract human-readable details from the JSON details field
      let details = "";
      try {
        const parsed = JSON.parse(a.details);
        details =
          parsed.alert ??
          parsed.reason ??
          parsed.error ??
          parsed.message ??
          a.details;
      } catch {
        details = a.details;
      }

      return {
        id: a.id,
        severity: a.severity,
        action: a.action,
        resourceName: a.resourceName ?? a.resource,
        details,
        createdAt: a.createdAt.toISOString(),
      };
    });

    return NextResponse.json({ alerts: formatted });
  } catch (error) {
    console.error("[/api/dashboard/sna-alerts GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch SNA alerts" },
      { status: 500 }
    );
  }
}
