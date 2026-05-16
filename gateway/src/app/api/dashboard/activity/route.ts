import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const logs = await db.auditLog.findMany({
      orderBy: { createdAt: "desc" },
      take: 20,
    });

    // Enrich with actor names from User table
    const actorIds = [...new Set(logs.map((l) => l.actorId).filter(Boolean))] as string[];
    const users = await db.user.findMany({
      where: { id: { in: actorIds } },
      select: { id: true, name: true },
    });
    const userMap = new Map(users.map((u) => [u.id, u.name]));

    const activities = logs.map((log) => ({
      id: log.id,
      action: log.action,
      actorName: log.actorId
        ? userMap.get(log.actorId) ?? log.actorId
        : log.actorType === "system"
          ? "System"
          : log.actorType,
      resource: log.resource,
      resourceName: log.resourceName ?? log.resource,
      outcome: log.outcome,
      severity: log.severity,
      createdAt: log.createdAt.toISOString(),
    }));

    return NextResponse.json({ activities });
  } catch (error) {
    console.error("[/api/dashboard/activity GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch activity feed" },
      { status: 500 }
    );
  }
}
